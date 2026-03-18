from saigon.iter import is_true_or_valid, first, contains, select


class TestIter:
    def test_is_true_or_valid(self):
        assert is_true_or_valid(True) is True
        assert is_true_or_valid(False) is False
        assert is_true_or_valid(1) is True
        assert is_true_or_valid("hello") is True
        # This is expected to fail based on current implementation
        assert is_true_or_valid(None) is False

    def test_first(self):
        items = [None, False, 0, 1, 2]
        # Default condition is is_true_or_valid
        # If None is True, it will return None
        # If None is False, False is False, 0 is True (not bool),
        # it should return 0
        assert first(items) == 0

        assert first([0, 1, 2], condition=lambda x: x > 1) == 2
        assert first([0, 1, 2], condition=lambda x: x > 5) is None

    def test_contains(self):
        assert contains([None, False, 1]) is True
        assert contains([None, False]) is False
        assert contains([1, 2, 3], condition=lambda x: x > 2) is True
        assert contains([1, 2, 3], condition=lambda x: x > 5) is False

    def test_select(self):
        items = [None, False, 1, "a", True]
        # is_true_or_valid(None) -> False
        # is_true_or_valid(False) -> False
        # is_true_or_valid(1) -> True
        # is_true_or_valid("a") -> True
        # is_true_or_valid(True) -> True
        assert list(select(items)) == [1, "a", True]

        assert list(
            select([1, 2, 3, 4], condition=lambda x: x % 2 == 0)
        ) == [2, 4]
