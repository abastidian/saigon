import typing
from typing import Optional, Any
import pytest
from saigon.fflags import FeatureFlags
from saigon.interface import KeyValueRepository


class MockRepo(KeyValueRepository):
    def __init__(self):
        self.data = {}

    def get_by_name(self, key_type: Any, key: str) -> Optional[Any]:
        return self.data.get(key)

    def set_by_name(self, key: str, value: Any) -> Optional[Any]:
        self.data[key] = value
        return value


class TestFeatureFlags:
    def test_fflags_initialization(self):

        repo = MockRepo()
        # Initialize the global repository on FeatureFlags
        FeatureFlags(repo)

        class MyFlags(FeatureFlags):
            FLAG1: typing.Callable[[], bool]

            def __init__(self, *args):
                super().__init__(MyFlags, *args)

        # We need to pass MyClass to MyFlags to get attributes on MyClass
        MyFlags()

        # Let's verify if FLAG1 is on MyClass
        assert hasattr(MyFlags, 'FLAG1')

        # Initially not set
        assert MyFlags.FLAG1() is None

        # Set it
        repo.set_by_name('FLAG1', True)
        assert MyFlags.FLAG1() is True

        # Change it
        repo.set_by_name('FLAG1', False)
        assert MyFlags.FLAG1() is False

    def test_fflags_setitem(self):
        from saigon.fflags import _FeatureFlagsMeta
        _FeatureFlagsMeta._repository = None

        repo = MockRepo()
        FeatureFlags(repo)

        # Test __setitem__ on FeatureFlags class
        FeatureFlags['FLAG2'] = "hello"
        assert repo.get_by_name(str, 'FLAG2') == "hello"

        # Test __getitem__
        assert FeatureFlags[str, 'FLAG2'] == "hello"

    def test_invalid_annotation(self):
        from saigon.fflags import _FeatureFlagsMeta
        _FeatureFlagsMeta._repository = None

        repo = MockRepo()
        FeatureFlags(repo)

        class MyClass:
            pass

        with pytest.raises(ValueError, match="invalid annotation"):
            class InvalidFlags(FeatureFlags):
                FLAG1: bool  # Not a Callable
            InvalidFlags(MyClass)
