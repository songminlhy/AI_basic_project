"""Simple CI smoke test - no external dependencies."""


def test_addition():
    assert 1 + 1 == 2


def test_string_uppercase():
    assert "hello".upper() == "HELLO"


def test_list_contains():
    items = [1, 2, 3]
    assert 2 in items
