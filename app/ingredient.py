"""Ingredient processing helpers.
"""

import re
import unicodedata
from fractions import Fraction

# Gracefully capture: [Qty1](-[Qty2])? [Unit/Food Name String]
# Evaluates ranges like "2-3", "1 1/2-2", or vulgar standalone numbers
QTY_RANGE_REGEX = re.compile(
    r'^(?:'
    r'(\d+)\s+(\d+/\d+)|(\d+/\d+)|(\d+)'     # First Quantity
    r')'
    r'(?:\s*-\s*'                            # Optional Range Dash Separator
    r'(?:(\d+)\s+(\d+/\d+)|(\d+/\d+)|(\d+))' # Second Quantity
    r')?\s*(.*)$'
)

UNICODE_FRACTIONS = {
    "1/2": "½", "1/3": "⅓", "2/3": "⅔", "1/4": "¼", "3/4": "¾",
    "1/5": "⅕", "2/5": "⅖", "3/5": "⅗", "4/5": "⅘", "1/6": "⅙",
    "5/6": "⅚", "1/8": "⅛", "3/8": "⅜", "5/8": "⅝", "7/8": "⅞"
}

UNIT_PLURAL_MAP = {
    'cups': 'cup', 'teaspoons': 'teaspoon', 'tsps': 'tsp',
    'tablespoons': 'tablespoon', 'tbsps': 'tbsp', 'ounces': 'ounce',
    'ozs': 'oz', 'pounds': 'pound', 'lbs': 'lb', 'cloves': 'clove',
    'pinches': 'pinch', 'cans': 'can', 'glasses': 'glass'
}

# Bidirectional conversions mapping directly to a multiplier ratio 
# and target singular word
# Trigger up at > 0.375 (so 1/4 tsp remains tsp)
UNIT_CONVERSIONS = {
    'cup': {'down': (16, 'tablespoon'), 'max': 8},
    'tablespoon': {
        'up': (1/16, 'cup'),
        'down': (3, 'teaspoon'),
        'max': 16,
        'min': 0.25,
    },
    'teaspoon': {'up': (1/3, 'tablespoon'), 'min': 0.375}
}


def normalize_unicode_fractions(text: str) -> str:
    """Convert mixed elements to standard math strings 1½ becomes 1 1/2.
    Ensures both 1½ and 1 ½ are valid.
    """
    spaced_text = re.sub(r'(?<=[\d])([½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞])', r' \1', text)
    # Decompose the unicode characters into standard text slashes safely
    normalized = unicodedata.normalize('NFKC', spaced_text).replace('\u2044', '/')
    return normalized


def float_to_nearest_quarter_fraction(val: float) -> Fraction:
    """Round float values to the nearest quarter/third fraction 
    with a min resolution of 1/4.
    """
    if val <= 0:
        return Fraction(0)
    
    # Check closer to thirds or quarters
    quarters = round(val * 4) / 4
    thirds = round(val * 3) / 3
    
    if abs(val - quarters) <= abs(val - thirds):
        return Fraction(quarters).limit_denominator(4)
    return Fraction(thirds).limit_denominator(3)


def format_fraction(frac: Fraction, sep: str = '') -> str:
    """Round fraction elements and reformat to standard unicode numbers.
    """
    if frac == 0:
        return ""
    whole = frac.numerator // frac.denominator
    rem = frac.numerator % frac.denominator
    
    if rem > 0:
        rem_frac = Fraction(rem, frac.denominator)
        frac_str = f"{rem_frac.numerator}/{rem_frac.denominator}"
        glyph = UNICODE_FRACTIONS.get(frac_str, frac_str)
        return f"{whole}{sep}{glyph}" if whole > 0 else glyph
    return str(whole)


def extract_unit_and_food(text_line: str) -> tuple[str, str]:
    """Extract unit keywords and return them directly after quantities. 
    
    Retains punctuation (like commas, dashes, or parentheses) intact. 
    """
    cleaned = text_line.strip()
    if not cleaned:
        return "", ""

    all_units = list(UNIT_PLURAL_MAP.keys()) + list(UNIT_PLURAL_MAP.values())
    all_units.sort(key=len, reverse=True)
    
    unit_pattern = re.compile(rf'\b({"|".join(all_units)})\b', re.IGNORECASE)
    
    match = unit_pattern.search(cleaned)
    if match:
        unit_found = match.group(1).lower()
        
        # Remove the unit word from the original string
        food_item = unit_pattern.sub('', cleaned, count=1)
        
        # Clean up multi-space gaps first
        food_item = re.sub(r'\s+', ' ', food_item).strip()
        
        # Remove any space that was accidentally trapped 
        # right before punctuation
        food_item = re.sub(r'\s+([,;.\)])', r'\1', food_item)
        
        if food_item.startswith(','):
            food_item = food_item.lstrip(',').strip()
            
        return unit_found, food_item

    return "", cleaned


def apply_unit_conversions(qty: float, unit: str) -> tuple[float, str]:
    """Convert small scale quantities down, large numbers up natively.
    """
    singular_unit = UNIT_PLURAL_MAP.get(unit.lower(), unit.lower())
    config = UNIT_CONVERSIONS.get(singular_unit)
    
    if not config:
        # Return singular unit instead of the raw incoming 'unit' string
        return qty, singular_unit 

    if 'down' in config and qty <= config.get('min', 0.125):
        multiplier, target = config['down']
        return apply_unit_conversions(qty * multiplier, target)

    if 'up' in config and qty >= config.get('max', 8):
        multiplier, target = config['up']
        return apply_unit_conversions(qty * multiplier, target)

    # Return singular unit
    return qty, singular_unit


def scale_ingredient_line(ingredient_line: str,
                          factor: float = 1.0,
                          sep: str = '') -> str:
    """Parse, standardize and scale an ingredient line.
    1. Uniformly repositions Unit directly after Quantities.
    2. Supports Min-Max Hyphenated Range Arrays dynamically.
    3. Handles scaling shifts between cooking units natively.
    """
    clean_line = ingredient_line.replace('((', '(').replace('))', ')')
    normalized = normalize_unicode_fractions(clean_line).strip()
    
    match = QTY_RANGE_REGEX.match(normalized)
    if not match:
        return clean_line

    # Extract dynamic matched regex block strings
    w1, f1, sf1, i1, w2, f2, sf2, i2, rest_text = match.groups()
    
    if not any([w1, f1, sf1, i1]):
        return clean_line

    # Build primary baseline values
    val1 = float(Fraction(w1 or i1 or 0) + Fraction(f1 or sf1 or 0)) * factor
    val2 = (float(Fraction(w2 or i2 or 0) + Fraction(f2 or sf2 or 0)) * factor 
            if any([w2, f2, sf2, i2]) else None)

    # Relocate unit position structures
    unit_raw, food_item = extract_unit_and_food(rest_text)

    # Run conversions using the calculated midpoint for range parameters
    eval_val = (val1 + val2) / 2 if val2 else val1
    
    if unit_raw:
        _, final_unit = apply_unit_conversions(eval_val, unit_raw)
        # Apply the resolved conversion ratios backwards 
        # onto individual quantities
        if final_unit != UNIT_PLURAL_MAP.get(unit_raw.lower(), unit_raw.lower()):
            singular_src = UNIT_PLURAL_MAP.get(unit_raw.lower(), unit_raw.lower())
            if ('down' in UNIT_CONVERSIONS.get(singular_src, {}) and 
                UNIT_CONVERSIONS[singular_src]['down'][1] == final_unit):
                ratio = UNIT_CONVERSIONS[singular_src]['down'][0]
            else:
                ratio = (UNIT_CONVERSIONS[final_unit]['down'][0] 
                         if final_unit in UNIT_CONVERSIONS else 1)
                ratio = 1 / ratio if ratio != 1 else 1
            val1 *= ratio
            if val2: 
                val2 *= ratio
    else:
        final_unit = ""

    # Format numeric portions into crisp fractions
    frac1 = float_to_nearest_quarter_fraction(val1)
    qty_str = format_fraction(frac1, sep=sep)
    
    if val2:
        frac2 = float_to_nearest_quarter_fraction(val2)
        qty_str = f"{qty_str}-{format_fraction(frac2, sep=sep)}"

    # Re-apply appropriate structural pluralization layout grammar suffixes
    if final_unit:
        is_plural = val1 > 1 or (val2 and val2 > 1)
        if is_plural:
            # Reverse-lookup the exact mapping plural spelling key
            final_unit = next(
                (k for k, v in UNIT_PLURAL_MAP.items() 
                 if v == final_unit),
                final_unit + 's'
            )
        else:
            # Force it to stay singular if quantity drops to 1 or below
            final_unit = UNIT_PLURAL_MAP.get(
                final_unit.lower(), final_unit.lower()
            )

    # Construct the final rearranged string text layout line
    components = [qty_str, final_unit, food_item]
    return " ".join([c for c in components if c]).strip()
