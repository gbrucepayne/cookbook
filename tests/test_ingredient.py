
from fractions import Fraction

import pytest

from app.ingredient import (
    Measurement,
    extract_measurement,
    format_fraction,
    normalize_unicode_fractions,
    scale_ingredient_line,
)


@pytest.mark.parametrize(
    "input, separator, expected",
    [
        ('1/2', None, '½'),
        ('3/2', None, '1½'),
        ('3/2', ' ', '1 ½'),
        ('2/3', None, '⅔'),
    ]
)
def test_format_fraction(input, separator, expected):
    """Test fraction formatting to unicode"""
    if separator is None:
        assert format_fraction(Fraction(input)) == expected
    else:
        assert format_fraction(Fraction(input), separator) == expected


@pytest.mark.parametrize(
    "input, expected",
    [
        ('½', '1/2'),
        ('1 ½', '1 1/2'),
        ('1½', '1 1/2'),
        ('1½ - 2', '1 1/2 - 2'),
        ('1½-2', '1 1/2 - 2'),
        ('0.66', '2/3'),
        ('1-1.5', '1 - 1 1/2'),
    ]
)
def test_normalize_unicode_fraction(input, expected):
    assert normalize_unicode_fractions(input) == expected


@pytest.mark.parametrize(
    "text, unit_abbr, expected_measurement",
    [
        ("pounds pork loin or chops", None, Measurement(1, None, 'pound', 'pork loin or chops')),
        ("tsp. kosher salt", None, Measurement(1, None, 'teaspoon', 'kosher salt')),
        ("tsp. kosher salt", True, Measurement(1, None, 'tsp', 'kosher salt')),
        ("c. vegetable oil", None, Measurement(1, None, 'cup', 'vegetable oil')),
        ("1/4 c. vegetable oil", None, Measurement(0.25, None, 'cup', 'vegetable oil')),
        ("1 1/2 tsp. kosher salt", None, Measurement(1.5, None, 'teaspoons', 'kosher salt')),
        ("can (15-oz) black beans", None, Measurement(1, None, 'can', '(15-oz) black beans')),
        ("5 pitted dates, chopped (or 3 large medjool)", None, Measurement(5, None, None, 'pitted dates, chopped (or 3 large medjool)')),
        ("3-5 pitted dates, chopped", None, Measurement(3, 5, None, 'pitted dates, chopped')),
        ("3 garlic cloves, minced", None, Measurement(3, None, 'cloves', 'garlic, minced')),
        ("Zest of 1 lemon", None, Measurement(1, None, None, 'lemon zest')),
        ("250g chicken", None, Measurement(250, None, 'grams', 'chicken')),
        ("250-300g\tchicken", None, Measurement(250, 300, 'grams', 'chicken')),
    ]
)
def test_extract_measurement(text, unit_abbr, expected_measurement):
    if unit_abbr is not None:
        assert extract_measurement(text, unit_abbr) == expected_measurement
    else:
        assert extract_measurement(text) == expected_measurement


@pytest.mark.parametrize(
    "input, scale, unit_abbr, expected",
    [
        ("1½ pounds pork loin or chops", 0.5, False, "¾ pound pork loin or chops"),
        ("1½ pounds pork loin or chops", 2, False, "3 pounds pork loin or chops"),
        ("1-2 tablespoons water (to thin)", 2, False, "2-4 tablespoons water (to thin)"),
        ("1-2 tablespoons water (to thin)", 0.5, False, "½-1 tablespoon water (to thin)"),
        ("1-1½ tablespoons water (to thin)", 2, False, "2-3 tablespoons water (to thin)"),
        ("1 - 2 tablespoons water (to thin)", 2, False, "2-4 tablespoons water (to thin)"),
        ("1 ½ pounds pork loin or chops ((cut into 1-inch pieces))", None, False, "1½ pounds pork loin or chops (cut into 1-inch pieces)"),
        ("¼ cup less-sodium soy sauce ((plus more if desired))", 2, False, "½ cup less-sodium soy sauce (plus more if desired)"),

        ("3 garlic cloves, minced", None, False, "3 cloves garlic, minced"),
        ("3 garlic cloves, minced", 1/3, False, "1 clove garlic, minced"),
        ("Zest of 1 lemon", 2, False, "2 lemon zest"),

        ("0.6667 cup stuff", None, False, "⅔ cup stuff"),
        ("1 tsp. kosher salt", None, False, "1 teaspoon kosher salt"),
        ("1 tsp. kosher salt", None, True, "1 tsp kosher salt"),
        ("1 15-ounce can black beans, drained and rinsed", None, True, "1 can (15-oz) black beans, drained and rinsed"),
        ("3 15-ounce cans green enchilada sauce", 1/2, True, "1½ cans (15-oz) green enchilada sauce"),
        ("1/4 cup vegetable oil", None, False, "¼ cup vegetable oil"),
        ("1/4 c. vegetable oil", None, False, "¼ cup vegetable oil"),
        ("161-mL can coconut milk", None, False, "1 can (161-ml) coconut milk"),
        ("1 14 or 15-oz can organic pumpkin", None, False, "1 can (15-oz) organic pumpkin"),
        ("2 cans (15-oz) coconut milk", None, False, "2 cans (15-oz) coconut milk"),
        ("675g chicken fillets, cut in half", None, False, "675 grams chicken fillets, cut in half"),

        ("5 pitted dates, chopped (or 3 large medjool)", None, False, "5 pitted dates, chopped (or 3 large medjool)"),
        
        ("# Section Heading", None, False, "# Section Heading"),
    ]
)
def test_scale_ingredient_line(input, scale, unit_abbr, expected):
    if isinstance(scale, (float, int)):
        assert scale_ingredient_line(input, scale, abbreviate_unit=unit_abbr) == expected
    else:
        assert scale_ingredient_line(input, abbreviate_unit=unit_abbr) == expected
