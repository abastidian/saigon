import pytest
from contextlib import ExitStack
from typing import Generator

from saigon.orm.connection import DbConnector
from saigon.orm.config import BaseDbEnv

from .infra import *

__all__ = [
    'execution_env',
    'db_connector',
    'exit_stack'
]


@pytest.fixture(scope='session', autouse=True)
def execution_env(request: pytest.FixtureRequest) -> ExecutionEnvironment:
    return request.config.option.env


@pytest.fixture(scope='session')
def db_connector(base_db_env: BaseDbEnv) -> DbConnector:
    return DbConnector(base_db_env.db_credentials)


@pytest.fixture(scope='function')
def exit_stack() -> Generator[ExitStack, None, None]:
    with ExitStack() as stack:
        yield stack
