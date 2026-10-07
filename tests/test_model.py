import pytest

from app.models import (
    to_recipe_title_case,
)


@pytest.mark.parametrize("input, expected_output", [
    ("apple pie", "Apple Pie"),
    ("APPLE PIE WITH CHEESE", "Apple Pie with Cheese"),
    ("GLUTEN-FREE RAMEN \"TO GO\"", "Gluten-Free Ramen \"To Go\""),
])
def test_to_recipe_title_case(input: str, expected_output: str):
    assert to_recipe_title_case(input) == expected_output
