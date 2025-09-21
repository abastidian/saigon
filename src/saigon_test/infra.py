import random
import uuid
import enum
import time
import pytest
from pathlib import Path
from enum import StrEnum, auto
from datetime import datetime
from dotenv import load_dotenv
from types import UnionType
from typing import (
    Type,
    Dict,
    Any,
    Callable,
    TypeVar,
    Optional,
    Union,
    get_origin,
    get_args,
    NewType,
    Generator,
    List
)

from saigon.model import ModelTypeDef
from saigon.utils import get_file_dir

from pydantic import BaseModel

__all__ = [
    'EXEC_ENV_OPTION_NAME',
    'ExecutionEnvironment',
    'include_all',
    'pytest_addoption',
    'mark_only_envs',
    'pytest_collection_modifyitems',
    'load_execution_env_vars',
    'make_test_model_data',
    'wait_for_condition',
    'GeneratorReturnValue'
]

_random = random.Random()

_ANY_TYPE = TypeVar('_ANY_TYPE')

GeneratorReturnValue = Generator[ModelTypeDef, None, None]

mark_only_envs = pytest.mark.exec_envs

EXEC_ENV_OPTION_NAME = 'env'


def include_all(exports: Optional[List[str]] = None) -> List[str]:
    return __all__ + (exports if exports else [])


class ExecutionEnvironment(StrEnum):
    LOCAL = auto()
    SBX = auto()
    PROD = auto()


def pytest_addoption(parser: pytest.Parser):
    if EXEC_ENV_OPTION_NAME in [opt.dest for opt in parser._anonymous.options]:
        return

    parser.addoption(
        f"--{EXEC_ENV_OPTION_NAME}",
        nargs='?',
        action="store",
        default=ExecutionEnvironment.LOCAL,
        type=ExecutionEnvironment
    )


def pytest_collection_modifyitems(
        config: pytest.Config, items: List[pytest.Item]
):
    execution_env = config.getvalue('env')
    for test_item in items:
        enabled_envs_marker = next(
            filter(
                lambda marker: marker.name == mark_only_envs.name,
                test_item.iter_markers()
            ),
            None
        )
        if enabled_envs_marker and execution_env not in enabled_envs_marker.args:
            test_item.add_marker(
                pytest.mark.skip(
                    reason=f"envs={[m.value for m in enabled_envs_marker.args]}"
                )
            )


def load_execution_env_vars(
        env_type: ExecutionEnvironment,
        parent_dir=Path('.')
):
    env_file_name = f"env.{env_type.value}"
    # find a location with env files
    env_file_path = Path(parent_dir, env_file_name)
    if not env_file_path.exists():
        env_file_path = Path(get_file_dir(__file__), env_file_name)

    if not load_dotenv(env_file_path):
        raise ValueError('could not load environment file')


def wait_for_condition[ResultType](
    condition: Callable[..., ResultType | None],
    max_retries=30
) -> ResultType:
    retry_count = 0
    while retry_count < max_retries:
        if result := condition():
            return result

        time.sleep(5)
        retry_count += 1

    raise TimeoutError('condition not met')


def make_test_model_data(
        model_type: Type[ModelTypeDef], **kwargs
) -> ModelTypeDef:
    return _generate_test_value(model_type, None, **kwargs)


def _generate_test_value(
        value_type: Type[_ANY_TYPE],
        member_name: Optional[str] = 'any',
        **kwargs
) -> _ANY_TYPE:
    if get_origin(value_type) == dict:
        dict_types = get_args(value_type)
        return {
            _generate_test_value(dict_types[0]): _generate_test_value(dict_types[1])
        }

    if get_origin(value_type) == list:
        list_type = get_args(value_type)
        return [_generate_test_value(list_type[0])]

    if get_origin(value_type) in [Union, UnionType]:
        union_type = get_args(value_type)
        return _generate_test_value(union_type[0])

    if value_type is NewType:
        return _generate_test_value(
            value_type.__supertype__, member_name
        )

    if issubclass(value_type, BaseModel):
        init_params = {}
        for name, finfo in value_type.model_fields.items():
            if (init_value := kwargs.get(name, None)) is None:
                init_value = _generate_test_value(
                    finfo.annotation, name
                )
            init_params[name] = init_value

        return value_type(**dict(init_params, **kwargs))

    if issubclass(value_type, enum.Enum):
        return [v.value for v in value_type][0]

    value_generator = _FIELD_VALUE_GENERATORS.get(
        value_type, lambda _: value_type()
    )
    return value_generator(member_name)


_FIELD_VALUE_GENERATORS: Dict[Type[Any], Callable] = {
    int: lambda _: _random.randint(0, 1000),
    float: lambda _: _random.randint(100, 200),
    str: lambda f_name: f"{f_name}_{_random.randint(0, 1000)}",
    datetime: lambda _: datetime.now(tz=None),
    uuid.UUID: lambda _: uuid.uuid4(),
    Any: lambda _: {}
}
