from fractions import Fraction

from app.ingredient import (
    format_fraction,
    normalize_unicode_fractions,
    scale_ingredient_line,
)


def test_format_fraction():
    """Test fraction formatting to unicode"""
    assert format_fraction(Fraction('1/2')) == '½'
    assert format_fraction(Fraction('1/2'), False) == '1/2'
    assert format_fraction(Fraction('3/2')) == '1½'
    assert format_fraction(Fraction('3/2'), sep=' ') == '1 ½'


def test_normalize_unicode_fraction():
    assert normalize_unicode_fractions('½') == '1/2'
    assert normalize_unicode_fractions('1 ½') == '1 1/2'
    assert normalize_unicode_fractions('1½') == '1 1/2'
    assert normalize_unicode_fractions('1½ - 2') == '1 1/2 - 2'
    assert normalize_unicode_fractions('1½-2') == '1 1/2 - 2'


def test_scale_ingredient_line():
    example = "1½ pounds pork loin or chops"
    assert scale_ingredient_line(example, 0.5) == '¾ pound pork loin or chops'
    assert scale_ingredient_line(example, 2) == '3 pounds pork loin or chops'
    range_example = "1-2 tablespoons water (to thin)"
    assert scale_ingredient_line(range_example, 2) == '2-4 tablespoons water (to thin)'
    assert scale_ingredient_line(range_example, 0.5) == '½-1 tablespoon water (to thin)'
    range_example_2 = "1-1½ tablespoons water (to thin)"
    assert scale_ingredient_line(range_example_2, 2) == '2-3 tablespoons water (to thin)'
    range_example_3 = "1 - 2 tablespoons water (to thin)"
    assert scale_ingredient_line(range_example_3, 2) == '2-4 tablespoons water (to thin)'
    example = '1 ½ pounds pork loin or chops ((cut into 1-inch pieces))'
    assert scale_ingredient_line(example) == '1½ pounds pork loin or chops (cut into 1-inch pieces)'
    example = '¼ cup less-sodium soy sauce ((plus more if desired))'
    assert scale_ingredient_line(example) == '¼ cup less-sodium soy sauce (plus more if desired)'
    example = '3 garlic cloves, minced'
    assert scale_ingredient_line(example) == '3 cloves garlic, minced'
    example = '3 garlic cloves, minced'
    assert scale_ingredient_line(example, 1/3) == '1 clove garlic, minced'
    example = 'Zest of 1 lemon'
    assert scale_ingredient_line(example, 2) == '2 lemons zest'
