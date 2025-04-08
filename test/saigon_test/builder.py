import random
from datetime import datetime
import uuid
import enum
import time
import pytest
from types import UnionType
from typing import (
    Type, Dict, Any, Callable, TypeVar, Optional, Union, get_origin, get_args, NewType
)

from saigon.orm.connection import DbConnector
from saigon.model import ModelTypeDef
from saigon.orm.config import BaseDbEnv

from pydantic import BaseModel

__all__ = [
    'make_test_model_data',
    'db_connector',
    'wait_for_condition'
]

_random = random.Random()

_ANY_TYPE = TypeVar('_ANY_TYPE')


@pytest.fixture()
def base_db_env() -> BaseDbEnv:
    db_env = BaseDbEnv('SAIGON')
    db_env.setvars()

    return db_env


@pytest.fixture(scope='session')
def db_connector(base_db_env) -> DbConnector:
    return DbConnector(base_db_env.db_credentials)


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

    raise TimeoutError(f"condition not met")


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

    if type(value_type) == NewType:
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

    value_generator = _field_value_generators.get(
        value_type, lambda _: value_type()
    )
    return value_generator(member_name)


_field_value_generators: Dict[Type[Any], Callable] = {
    int: lambda _: _random.randint(0, 1000),
    float: lambda _: _random.randint(100, 200),
    str: lambda f_name: f"{f_name}_{_random.randint(0, 1000)}",
    datetime: lambda _: datetime.now(tz=None),
    uuid.UUID: lambda _: uuid.uuid4(),
    Any: lambda _: {}
}
