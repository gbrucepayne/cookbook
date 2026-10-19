"""Ingredient processing helpers.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction

logger = logging.getLogger(__name__)

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
    'cups': 'cup',
    'teaspoons': 'teaspoon',
    'tsps': 'tsp',
    'tablespoons': 'tablespoon',
    'tbsps': 'tbsp',
    'ounces': 'ounce',
    'ozs': 'oz',
    'pounds': 'pound',
    'lbs': 'lb',
    'cloves': 'clove',
    'pinches': 'pinch',
    # 'cans': 'can',
    # 'glasses': 'glass',
    # 'packages': 'package',
    # 'containers': 'container',
}

UNIT_MAP = {
    'c': 'cup',
    'cs': 'cup',
    'cup': 'cup',
    'cups': 'cup',
    'tbsp': 'tablespoon',
    'tablespoon': 'tablespoon',
    'tablespoons': 'tablespoon',
    'tsp': 'teaspoon',
    'tsps': 'teaspoon',
    'teaspoon': 'teaspoon',
    'teaspoons': 'teaspoon',
    'oz': 'ounce',
    'ozs': 'ounce',
    'ounce': 'ounce',
    'ounces': 'ounce',
    'lb': 'pound',
    'lbs': 'pound',
    'pound': 'pound',
    'pounds': 'pound',
    'ml': 'millilitre',
    'milliliter': 'millilitre',
    'milliliters': 'millilitre',
    'millilitre': 'millilitre',
    'millilitres': 'millilitre',
    'l': 'litre',
    'liter': 'litre',
    'liters': 'litre',
    'litre': 'litre',
    'litres': 'litre',
    'g': 'gram',
    'gram': 'gram',
    'grams': 'gram',
    'kg': 'kilogram',
    'kilogram': 'kilogram',
    'kilograms': 'kilogram',
    'clove': 'clove',
    'cloves': 'clove',
    'pinch': 'pinch',
    'pinches': 'pinch',
    'glass': 'glass',
    'glasses': 'glass',
}

UNIT_PLURALS = {
    'pinch': 'pinches',
    'ml': 'ml',
    'l': 'l',
    'g': 'g',
    'kg': 'kg',
}

UNIT_CONTAINERS = {
    'can', 'cans',
    'package', 'packages',
    'glass', 'glasses',
    'container', 'containers',
}

CONTAINER_MAP = {
    'can': 'can',
    'cans': 'can',
    'package': 'package',
    'packages': 'package',
    'glass': 'glass',
    'glasses': 'glass',
}

ABBREVIATIONS = {
    'teaspoon': 'tsp',
    'tablespoon': 'tbsp',
    'ounce': 'oz',
    'pound': 'lb',
    'millilitre': 'ml',
    'litre': 'l',
}

UNIT_ABBREVIATION_MAP = {
    'c': 'cup',
    'tsp': 'teaspoon',
    'tsps': 'teaspoons',
    'tbsp': 'tablespoon',
    'tbsps': 'tablespoons',
    'oz': 'ounce',
    'ozs': 'ounces',
    'lb': 'pound',
    'lbs': 'pounds',
}

# Bidirectional conversions mapping directly to a multiplier ratio 
# and target singular word
# Trigger up at > 0.375 (so 1/4 tsp remains tsp)
UNIT_CONVERSIONS = {
    'cup': {
        'down': (16, 'tablespoon'),
        'max': 8,
    },
    'tablespoon': {
        'up': (1/16, 'cup'),
        'down': (3, 'teaspoon'),
        'max': 16,
        'min': 0.25,
    },
    'teaspoon': {
        'up': (1/3, 'tablespoon'),
        'min': 0.375,
    }
}


# @dataclass
# class IngredientContainer:
#     name: str
#     quantity: float | None = None
#     unit: str | None = None
#     food_item: str | None = None


def reorder_cooking_terms(text: str) -> str:
    """
    Transforms phrases like 'zest of 1 lemon' into '1 lemon zest' natively.
    Works for common preparations like zest, juice, rind, peel, segment, and grated.
    """
    # Define common preparatory cooking terms
    terms_pool = r"(zest|juice|peel|rind|grated\s+peel|segments?|seeds?)"
    
    # Pattern structures: [Term] + optional space + 'of' + optional space + [Quantity] + [Ingredient Name]
    reorder_pattern = re.compile(rf"""
        \b{terms_pool}\b                      # Capture Group 1: The preparatory action term
        \s+ of \s+                             # Match the literal linking word 'of' surrounded by spaces
        (                                      # Capture Group 2: The Quantity block
            \d+ \s* - \s* \d+                  # Matches ranges like '1 - 2'
            | \d*\.?\d+                        # Or standard integers/decimals like '1' or '0.5'
            | [½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]                # Or standalone unicode vulgar glyph assets
        )
        \s+                                    # Trailing space separation spacer
        ([^,\n]+)                              # Capture Group 3: The targeted baseline ingredient text string
    """, re.VERBOSE | re.IGNORECASE)

    def rearrange_and_lowercase(match):
        term = match.group(1).lower()
        qty = match.group(2)
        ingredient = match.group(3).strip()
        return f"{qty} {ingredient} {term}"
    
    # 3. Rearrange the layout groups: \2 (Quantity) + \3 (Ingredient) + \1 (Term)
    return reorder_pattern.sub(rearrange_and_lowercase, text.strip())


def convert_floats_to_fractions(text: str) -> str:
    """Convert leading quantity to a printable fraction."""
    words = text.strip().split(' ')
    for i, word in enumerate(words):
        try:
            words[i] = format_fraction(float_to_nearest_fraction(float(word)))
        except ValueError:
            continue
    return ' '.join(words)


def convert_to_float(text: str) -> float:
    """Convert a numeric string to floating point."""
    cleaned = text.strip().replace('-', ' ')
    parts = cleaned.split()
    if len(parts) == 2:
        whole_part = float(Fraction(parts[0]))
        frac_part = float(Fraction(parts[1]))
        return whole_part + frac_part
    elif len(parts) == 1:
        return float(Fraction(parts[0]))
    raise ValueError(f"Invalid numeric string format: '{text}")


def normalize_unicode_fractions(text: str) -> str:
    """Convert mixed elements to standard math strings 1½ becomes 1 1/2.
    Ensures both 1½ and 1 ½ are valid.
    """
    range_pattern = re.compile(r"""
        ^                        # Match only at the start of the string
        (                        # Start of Capture Group 1 (First Quantity)
            \d*                  # Optional whole digits
            \.?                  # Optional decimal point
            \d*                  # Optional fractional digits
            [½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]?   # Optional unicode fraction glyph
        )                        # End of Capture Group 1
        \s* - \s*                # Match range marker ignoring surrounding spaces
        (                        # Start of Capture Group 2 (Second Quantity)
            \d*                  # Optional whole digits
            \.?                  # Optional decimal point
            \d*                  # Optional fractional digits
            [½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]?   # Optional unicode fraction glyph
        )                        # End of Capture Group 2
    """, re.VERBOSE)
    single_quantity_pattern = re.compile(r"""
        ^                        # Match only at the start of the string
        (                        # Start of Capture Group 1
            \d*                  # Optional whole digits
            \.?                  # Optional decimal point
            \d*                  # Optional fractional digits
            [½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]?   # Optional unicode fraction glyph
        )                        # End of Capture Group 1
        (?=[A-Za-z])             # Lookahead: followed immediately by a unit letter
    """, re.VERBOSE)
    cleaned = reorder_cooking_terms(text.strip())
    cleaned = re.sub(range_pattern, r'\1 - \2', cleaned)
    cleaned = re.sub(single_quantity_pattern, r'\1', cleaned)
    cleaned = cleaned.replace('  ', ' ')
    cleaned = convert_floats_to_fractions(cleaned)
    spaced_text = re.sub(r'(?<=[\d])([½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞])', r' \1', cleaned)
    # Decompose the unicode characters into standard text slashes safely
    normalized = unicodedata.normalize('NFKC', spaced_text)
    return normalized.replace('\u2044', '/')


def float_to_nearest_fraction(val: float, min_res: float = 1/4) -> Fraction:
    """Round float values to the nearest quarter/third fraction 
    with a min resolution of 1/4.
    """
    if val <= 0:
        return Fraction(0)
    
    # Check closest
    eighths = round(val * 8) / 8
    quarters = round(val * 4) / 4
    thirds = round(val * 3) / 3
    halves = round(val * 2) / 2
    
    if min_res < 1/4 and abs(val - eighths) <= abs(val - quarters):
        return Fraction(eighths).limit_denominator(8)
    if min_res < 1/3 and abs(val - quarters) <= abs(val - thirds):
        return Fraction(quarters).limit_denominator(4)
    if min_res < 1/2 and abs(val - thirds) <= abs(val - halves):
        return Fraction(thirds).limit_denominator(3)
    return Fraction(halves).limit_denominator(2)


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


@dataclass
class UnitConversion:
    qty: float
    unit: str
    ratio: float = 1.0


def apply_unit_conversions(qty: float, unit: str) -> UnitConversion:
    """Convert small scale quantities down, large numbers up natively.
    """
    base_unit = UNIT_PLURAL_MAP.get(unit.lower(), unit.lower())
    config = UNIT_CONVERSIONS.get(base_unit, {})
    conversion = UnitConversion(qty, base_unit)
    
    if config:
        if 'down' in config and qty <= config.get('min', 0.125):
            multiplier, new_unit = config['down']
        elif 'up' in config and qty > config.get('max', 8):
            multiplier, new_unit = config['up']
        else:
            multiplier, new_unit = 1, base_unit
        if new_unit != base_unit:
            conversion.qty *= multiplier
            conversion.unit = new_unit
            conversion.ratio = multiplier
    return conversion


@dataclass
class Measurement:
    qty: float = 1.0
    unit: str | None = None
    item: str | None = None


def extract_measurement(text: str, unit_abbr: bool = False) -> Measurement|None:
    """Extract a quantity, unit and item from an ingredient line.
    
    * Allows abbreviated units with optional period e.g. `tsp.`
    * Allows single-character abbreviations e.g. `g`
    """
    cleaned = text.strip()
    single_chars = [u for u in UNIT_MAP if len(u) == 1]
    single_pattern = '|'.join(re.escape(u) for u in single_chars)
    multi_chars = sorted([u for u in UNIT_MAP | CONTAINER_MAP if len(u) > 1],
                         key=len,
                         reverse=True)
    multi_pattern = '|'.join(re.escape(u) for u in multi_chars)
    
    # Optional quantity integers, decimals, 
    # fractions (1/4) and mixed fractions (1 1/2)
    qty_pattern = r"(\d+\s+\d+/\d+|\d+/\d+|\d+\.\d+|\d+)\s*-?\s*"
    
    # Look-around boundary rules when quantity is present
    single_bnd_pattern = (rf"(?:(?<=\s)|(?<=\d)|(?<=/)|-|\b)"
                          rf"({single_pattern})(?:\b|\.?)")
    multi_bnd_pattern = rf"\b({multi_pattern})\b\.?"
    
    # Combined Regex matcher:
    # Group 1: Quantity (optional)
    # Group 2: Single-char Unit (optional `.` suffix), with quantity
    # Group 3: Multi-char Unit (optional `.` suffix), with quantity
    # Group 4: Multi-char unit (optional `.` suffix), no quantity
    # Group 5: Single-char unit (required `.` suffix), no quantity
    regex = re.compile(
        rf"(?:{qty_pattern}(?:{single_bnd_pattern}|{multi_bnd_pattern}))"
        # rf"(?:{qty_pattern}\b({single_bnd_pattern}|{multi_bnd_pattern})\b\.?)"
        rf"|\b({multi_pattern})\b\.?"
        rf"|\b({single_pattern})\.",
        re.IGNORECASE
    )
    match = regex.search(cleaned)
    if not match:
        return None
    
    if match.group(1):
        raw_qty = match.group(1)
        quantity = convert_to_float(raw_qty)
        raw_unit = (match.group(2) or match.group(3)).lower()
    elif match.group(4):
        quantity = 1.0
        raw_unit = match.group(4).lower()
    else:
        quantity = 1.0
        raw_unit = match.group(5).lower()
    base_unit = UNIT_MAP.get(raw_unit, CONTAINER_MAP.get(raw_unit, 'unit'))
    if unit_abbr:
        base_unit = ABBREVIATIONS.get(base_unit, base_unit)
    if quantity > 1.0:
        final_unit = UNIT_PLURALS.get(base_unit, f"{base_unit}s")
    else:
        final_unit = base_unit
    
    start, end = match.span()
    left_side = cleaned[:start]
    right_side = cleaned[end:]
    remaining_text = f"{left_side} {right_side}"
    remaining_text = re.sub(r'\s+', ' ', remaining_text)
    remaining_text = re.sub(r'^\s*,\s*|\s*,\s*$', '', remaining_text)
    remaining_text = remaining_text.strip('(),. ')
    
    # Remove the unit word from the original string
    food_item = regex.sub('', cleaned, count=1).strip()
    if food_item:
        # Remove any abbreviation indicator
        if food_item.startswith('. '):
            food_item = food_item.replace('. ', '', 1)
        # Clean up multi-space gaps first
        food_item = re.sub(r'\s+', ' ', food_item).strip()
        # Remove any space that was accidentally trapped before punctuation
        food_item = re.sub(r'\s+([,;.\)])', r'\1', food_item)
        # Remove leading commas
        if food_item.startswith(','):
            food_item = food_item.lstrip(',').strip()
    
    return Measurement(quantity, final_unit, food_item)


def reformat_container(clean_line: str, unit_abbr: bool = True) -> str:
    """Reformat a container included in the ingredient line.
    To always produce something like <container_count> <container_name>
    (<container_quantity>-<container_unit_abbr>)
    """
    words  = [w.strip() for w in clean_line.split(' ') if w.strip()]
    if not any(c_word.lower() in words for c_word in CONTAINER_MAP):
        return clean_line
    try:
        qty = int(words[0])
        words = words[1:]
    except ValueError:
        qty = 1
    for idx, word in enumerate(words):
        base_container = CONTAINER_MAP.get(word, None)
        if base_container:
            if qty > 1:
                base_container = UNIT_PLURALS.get(base_container,
                                                  f"{base_container}s")
            # Assume container measurement is either immediately before or
            # immediately after the container word
            meas = None
            if idx == 0 and idx + 1 < len(words):
                # Check immediately after container name
                candidate = words[idx + 1].strip('[](){}')
                meas = extract_measurement(candidate)
                if meas:
                    # Clear the parsed value
                    words[idx + 1] = ''
            if not meas and idx > 0:
                # Check before container name clearing all non-measurements
                for rem_idx in range(idx):
                    candidate = words[rem_idx].strip('[](){}')
                    meas = extract_measurement(candidate)
                    words[rem_idx] = ''
            reformatted = base_container
            if meas:
                final_unit = UNIT_MAP.get(meas.unit, meas.unit)
                if unit_abbr:
                    final_unit = ABBREVIATIONS.get(final_unit, final_unit)
                reformatted = f"{reformatted} ({int(meas.qty)}-{final_unit})"
            words[idx] = reformatted
            words = words[idx:]
            break
    return f"{qty} {' '.join([w.strip() for w in words if w.strip()])}"


def reformat_single_char_units(text: str) -> str:
    """Ensure single-character unit abbreviations use `.` suffix."""
    words = text.split(' ')
    for idx, word in enumerate(words):
        if len(word) == 1 and word in UNIT_MAP:
            words[idx] = f"{word}."
    return ' '.join(words)


def scale_ingredient_line(ingredient_line: str,
                          factor: float = 1.0,
                          fraction_sep: str = '',
                          abbreviate_unit: bool = False) -> str:
    """Parse, standardize and scale an ingredient line.
    1. Uniformly repositions Unit directly after Quantities.
    2. Supports Min-Max Hyphenated Range Arrays dynamically.
    3. Handles scaling shifts between cooking units natively.
    """
    # Remove duplicate brackets used in some encodings
    clean_line = ingredient_line.replace('((', '(').replace('))', ')').strip()
    # Ensure single-character abbreviations can be identified in regex
    clean_line = reformat_single_char_units(clean_line)
    # Ensure consistent formatting of containerized food items `1 can (15-oz)`
    clean_line = reformat_container(clean_line)
    normalized = normalize_unicode_fractions(clean_line).strip()
    
    match = QTY_RANGE_REGEX.match(normalized)
    if not match:
        return clean_line

    # Extract dynamic matched regex block strings:
    # mixed fractions: w: whole part, f: fraction part
    # standalone fractions: sf, standalone integers: i
    w1, f1, sf1, i1, w2, f2, sf2, i2, rest_text = match.groups()
    
    if not any([w1, f1, sf1, i1]):
        return clean_line

    # Build primary baseline values
    val1 = float(Fraction(w1 or i1 or 0) + Fraction(f1 or sf1 or 0)) * factor
    val2 = (float(Fraction(w2 or i2 or 0) + Fraction(f2 or sf2 or 0)) * factor 
            if any([w2, f2, sf2, i2]) else None)

    # Relocate unit position structures
    # unit_raw, food_item = extract_unit_and_food(rest_text)
    meas = extract_measurement(reformat_single_char_units(rest_text))
    food_item = meas.item if meas and meas.item else rest_text

    if meas and meas.unit: # unit_raw:
        # Run conversions using the calculated midpoint for range parameters
        eval_val = (val1 + val2) / 2 if val2 else val1    
        base_unit = UNIT_MAP.get(meas.unit, meas.unit)
        conversion = apply_unit_conversions(eval_val, base_unit)
        if val2:
            val1 *= conversion.ratio
            val2 *= conversion.ratio
        else:
            val1 = conversion.qty
        final_unit = conversion.unit
    else:
        final_unit = ""

    # Format numeric portions into crisp fractions
    frac1 = float_to_nearest_fraction(val1)
    qty_str = format_fraction(frac1, sep=fraction_sep)
    
    if val2:
        frac2 = float_to_nearest_fraction(val2)
        qty_str = f"{qty_str}-{format_fraction(frac2, sep=fraction_sep)}"

    # Re-apply appropriate structural pluralization layout grammar suffixes
    if final_unit:
        if abbreviate_unit:
            final_unit = ABBREVIATIONS.get(final_unit, final_unit)
        is_plural = val1 > 1 or (val2 and val2 > 1)
        if is_plural:
            final_unit = UNIT_PLURALS.get(final_unit, f"{final_unit}s")

    # Construct the final rearranged string text layout line
    components = [qty_str, final_unit, food_item]
    cleaned = " ".join([c for c in components if c]).strip()
    cleaned = cleaned.replace(' , ', ', ')
    return cleaned
