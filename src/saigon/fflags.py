import typing
from typing import Optional, Tuple, Type, Callable, TypeVar

from .interface import KeyValueRepository

__all__ = ['FeatureFlags', 'FlagGetter']


FlagTypeDef = TypeVar('FlagTypeDef', bound=KeyValueRepository.ValueType)
FlagGetter = Callable[[], FlagTypeDef]


class _FeatureFlagsMeta(type):
    _repository: KeyValueRepository = None

    def __call__(cls, *args, **kwargs):
        if _FeatureFlagsMeta._repository is None:
            _FeatureFlagsMeta._repository = args[0]
            super().__call__(*args, **kwargs)

    def __getitem__(
            cls, flag_spec: Tuple[KeyValueRepository.ValueType, str]
    ) -> Optional[KeyValueRepository.ValueType]:
        if not isinstance(flag_spec[0], type):
            raise ValueError('flag type not provided')

        return _FeatureFlagsMeta._repository.get_by_name(flag_spec[0], flag_spec[1])

    def __setitem__(cls, flag_name, flag_value):
        _FeatureFlagsMeta._repository.set_by_name(flag_name, flag_value)


class FeatureFlags(metaclass=_FeatureFlagsMeta):
    def __init__(self, class_type: Type, *args, **kwargs):
        for key, value in self.__class__.__annotations__.items():
            if not isinstance(value, Callable):
                raise ValueError('invalid annotation for flag definition')
            # The actual flag type is the return type of the callable annotation
            flag_type = typing.get_args(value)[1]
            setattr(
                class_type, key, lambda: FeatureFlags[flag_type, key]
            )
