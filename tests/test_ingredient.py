
from fractions import Fraction

import pytest

from app.ingredient import (
    extract_unit_and_food,
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
    ]
)
def test_normalize_unicode_fraction(input, expected):
    assert normalize_unicode_fractions(input) == expected


@pytest.mark.parametrize(
    "input, expected_unit, expected_food",
    [
        ("pounds pork loin or chops", "pound", "pork loin or chops"),
        ("tsp. kosher salt", "teaspoon", "kosher salt"),
        ("15-ounce can black beans", "can", "(15-oz) black beans"),
        ("c. vegetable oil", "cup", "vegetable oil"),
    ]
)
def test_extract_unit_and_food(input, expected_unit, expected_food):
    assert extract_unit_and_food(input) == (expected_unit, expected_food)


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
    ]
)
def test_scale_ingredient_line(input, scale, unit_abbr, expected):
    if isinstance(scale, (float, int)):
        assert scale_ingredient_line(input, scale, abbreviate_unit=unit_abbr) == expected
    else:
        assert scale_ingredient_line(input, abbreviate_unit=unit_abbr) == expected
