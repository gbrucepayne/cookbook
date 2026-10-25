"""Ingredient processing helpers.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction

logger = logging.getLogger(__name__)

UNICODE_FRACTIONS = {
    "1/2": "½", "1/3": "⅓", "2/3": "⅔", "1/4": "¼", "3/4": "¾",
    "1/5": "⅕", "2/5": "⅖", "3/5": "⅗", "4/5": "⅘",
    "1/6": "⅙", "5/6": "⅚",
    "1/8": "⅛", "3/8": "⅜", "5/8": "⅝", "7/8": "⅞",
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
    'handful': 'handful',
    'handfuls': 'handful',
    'bunch': 'bunch',
    'bunches': 'bunch',
}

UNIT_PLURALS = {
    'pinch': 'pinches',
    'ml': 'ml',
    'l': 'l',
    'g': 'g',
    'kg': 'kg',
}

CONTAINER_MAP = {
    'can': 'can',
    'cans': 'can',
    'package': 'package',
    'packages': 'package',
}

ABBREVIATIONS = {
    'teaspoon': 'tsp',
    'tablespoon': 'tbsp',
    'ounce': 'oz',
    'pound': 'lb',
    'millilitre': 'ml',
    'litre': 'l',
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


def pluralize(unit: str) -> str:
    """Pluralize a unit of measure."""
    base_unit = (UNIT_MAP | CONTAINER_MAP).get(unit, unit)
    if base_unit in UNIT_PLURALS:
        return UNIT_PLURALS.get(base_unit)
    if base_unit.endswith('s') and not base_unit.endswith('es'):
        return f"{base_unit}es"
    return f"{base_unit}s"


def reorder_cooking_terms(text: str) -> str:
    """
    Transforms phrases like 'zest of 1 lemon' into '1 lemon zest' natively.
    
    Works for common preparations like zest, juice, rind, 
    (grated) peel, segments, seeds.
    """
    # Define common preparatory cooking terms
    terms_pool = r"(zest|juice|peel|rind|grated\s+peel|segments?|seeds?)"
    
    # Pattern structures: [Term] + optional space + 'of' + optional space + [Quantity] + [Ingredient Name]
    reorder_pattern = re.compile(rf"""
        \b{terms_pool}\b          # Group 1: The preparatory action term
        \s+ of \s+                # Match the linking word 'of' surrounded by spaces
        (                         # Group 2: The Quantity block
            \d+ \s* - \s* \d+     # Matches ranges like '1 - 2'
            | \d*\.?\d+           # Or standard integers/decimals like '1' or '0.5'
            | [½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]   # Or standalone unicode vulgar glyph assets
        )
        \s+                       # Trailing space separation spacer
        ([^,\n]+)                 # Group 3: The baseline ingredient text string
    """, re.VERBOSE | re.IGNORECASE)

    def rearrange_and_lowercase(match):
        term = match.group(1).lower()
        qty = match.group(2)
        ingredient = match.group(3).strip()
        return f"{qty} {ingredient} {term}"
    
    # 3. Rearrange the layout groups: \2 (Quantity) + \3 (Ingredient) + \1 (Term)
    return reorder_pattern.sub(rearrange_and_lowercase, text.strip())


def convert_floats_to_fractions(text: str) -> str:
    """Convert decimal value(s) in a string to a printable fraction(s)."""
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
    """Convert mixed elements to standard math strings e.g. 1½ becomes 1 1/2.
    
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
    cleaned = re.sub(range_pattern, r'\1 - \2', text.strip())
    cleaned = re.sub(single_quantity_pattern, r'\1', cleaned)
    # Remove extraneous whitespace
    cleaned = ' '.join(cleaned.split())
    cleaned = convert_floats_to_fractions(cleaned)
    spaced_text = re.sub(r'(?<=[\d])([½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞])', r' \1', cleaned)
    # Decompose the unicode characters into standard text slashes safely
    normalized = unicodedata.normalize('NFKC', spaced_text)
    return normalized.replace('\u2044', '/')


def float_to_nearest_fraction(val: float, min_res: float = 1/4) -> Fraction:
    """Round float values to the nearest cooking measurement fraction. 
    
    Args:
        val: The numeric value to be converted.
        min_res (optional): The minimum resolution. Defaults to 1/4.
    
    Returns:
        The nearest `Fraction` value.
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
    
    Args:
        frac: The Fraction to reformat.
        sep (optional): Separator between whole/fraction parts. Default none.
    """
    if not isinstance(frac, Fraction) or frac == 0:
        return ''
    whole = frac.numerator // frac.denominator
    rem = frac.numerator % frac.denominator
    if rem > 0:
        if sep not in {'', ' '}:
            raise ValueError(f"Invalid separator {sep}")
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
    base_unit = UNIT_MAP.get(unit.lower(), unit.lower())
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
    qty_max: float | None = None
    unit: str | None = None
    item: str | None = None


def extract_measurement(line: str, unit_abbr: bool = False) -> Measurement|None:
    """Extract a quantity, unit and item from an ingredient line.
    
    * Extract quantity range [qty1][-qty2] [unit] [food item]
    * Allows abbreviated units with optional period e.g. `tsp.`
    * Allows single-character abbreviations e.g. `g` which must terminate
    with a period, space or the end of the line.
    
    Args:
        line: The ingredient line to parse.
        unit_abbr (optional): Set to abbreviate unit e.g. `tsp`
    """
    # Remove duplicate brackets used in some encodings
    cleaned = line.replace('((', '(').replace('))', ')').strip()
    # Ensure consistent formatting of containerized food items `1 can (15-oz)`
    cleaned = reformat_container(cleaned)
    cleaned = reorder_cooking_terms(cleaned)
    # Convert decimals and unicode to standard mixed fractions e.g. `1 1/2`
    cleaned = normalize_unicode_fractions(cleaned).strip()
    meas = Measurement()

    # Extract quantity [Qty1](-[Qty2])? [Unit/Food Name String]
    # Evaluates ranges like "2-3", "1 1/2-2", or standalone numbers
    # 1: mw1 mixed fraction, whole part (\d+)
    # 2: mf1 mixed fraction, fraction part \s+(\d+/\d+)
    # 3: f1 standalone fraction (\d+/\d+)
    # 4: w1 standalone whole number (\d+)
    # 5: mw2 mixed fraction, whole part 2nd quantity
    # 6: mf2 mixed fraction, fraction part 2nd quantity
    # 7: f2 standalone fraction 2nd quantity
    # 8: w2 standalone whole number 2nd quantity
    # 9: trailing text
    qty_range_pattern = re.compile(r"""
        ^(?:(\d+)\s+(\d+/\d+)|(\d+/\d+)|(\d+))             # 1st Quantity
        (?:\s*-\s*(?:(\d+)\s+(\d+/\d+)|(\d+/\d+)|(\d+)))   # Dash 2nd Quantity
        ?\s*(.*)$                                          # Remaining text
    """, re.VERBOSE)
    qty_match = qty_range_pattern.match(cleaned)
    if qty_match:
        mw1, mf1, f1, w1, mw2, mf2, f2, w2, cleaned = qty_match.groups()
        if any([mw1, f1, w1]):
            meas.qty = float(Fraction(mw1 or w1 or 0) + 
                             Fraction(mf1 or f1 or 0))
            if any([mw2, f2, w2]):
                meas.qty_max = float(Fraction(mw2 or w2 or 0) + 
                                     Fraction(mf2 or f2 or 0)) 
    
    # Extract unit
    single_chars = [u for u in UNIT_MAP if len(u) == 1]
    single_pattern = '|'.join(re.escape(u) for u in single_chars)
    multi_chars = sorted([u for u in UNIT_MAP | CONTAINER_MAP if len(u) > 1],
                         key=len,
                         reverse=True)
    multi_pattern = '|'.join(re.escape(u) for u in multi_chars)
    regex = re.compile(rf"""
        \b({multi_pattern})\b\.?
        |\b({single_pattern})\.?(?=\s|$)
    """, re.VERBOSE | re.IGNORECASE)
    match = regex.search(cleaned)
    if match:
        raw_unit = (match.group(1) or match.group(2)).lower()
        base_unit = UNIT_MAP.get(raw_unit, CONTAINER_MAP.get(raw_unit))
        if base_unit:
            if unit_abbr:
                base_unit = ABBREVIATIONS.get(base_unit, base_unit)
            if meas.qty > 1 or (meas.qty_max and meas.qty_max > 1):
                meas.unit = pluralize(base_unit)
            else:
                meas.unit = base_unit
        # Remove parsed elements from food item
        start, end = match.span()
        left_side = cleaned[:start]
        right_side = cleaned[end:]
        cleaned = f"{left_side} {right_side}".strip()
    
    if cleaned:
        # Remove any abbreviation indicator
        if cleaned.startswith('. '):
            cleaned = cleaned.replace('. ', '', 1)
        # Clean up multi-space gaps first
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        # Remove any space that was accidentally trapped before punctuation
        cleaned = re.sub(r'\s+([,;.\)])', r'\1', cleaned)
        # Remove leading commas
        if cleaned.startswith(','):
            cleaned = cleaned.lstrip(',').strip()
        meas.item = cleaned
        return meas
    
    return None


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
                base_container = pluralize(base_container)
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


def scale_ingredient_line(ingredient_line: str,
                          factor: float = 1.0,
                          fraction_sep: str = '',
                          abbreviate_unit: bool = False) -> str:
    """Parse, standardize and scale an ingredient line.
    1. Uniformly repositions Unit directly after Quantities.
    2. Supports Min-Max Hyphenated Range Arrays dynamically.
    3. Handles scaling shifts between cooking units natively.
    """
    cleaned = ingredient_line.strip()
    if cleaned.startswith('# '):
        return cleaned
    meas = extract_measurement(cleaned)
    if not meas:
        return cleaned
    
    food_item = meas.item
    # TODO: check if approximate total is in food_item, to scale it too
    val1 = meas.qty * factor
    val2 = meas.qty_max * factor if meas.qty_max else None
    
    if meas.unit:
        # Run conversions using the calculated midpoint for range parameters
        eval_val = (val1 + val2) / 2 if val2 else val1    
        base_unit = (UNIT_MAP | CONTAINER_MAP).get(meas.unit, meas.unit)
        conversion = apply_unit_conversions(eval_val, base_unit)
        if val2:
            val1 *= conversion.ratio
            val2 *= conversion.ratio
        else:
            val1 = conversion.qty
        final_unit = conversion.unit
    else:
        final_unit = ''

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
        if val1 > 1 or (val2 and val2 > 1):
            final_unit = pluralize(final_unit)

    # Construct the final rearranged string text layout line
    components = [qty_str, final_unit, food_item]
    cleaned = " ".join([c for c in components if c]).strip()
    # cleaned = cleaned.replace(' , ', ', ')
    return cleaned
