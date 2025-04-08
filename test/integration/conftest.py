import os
from dotenv import load_dotenv
import pathlib
import pytest

from sqlalchemy import Table

from saigon.orm.connection import DbConnector, AbstractDbManager
from saigon.orm.config import PostgreSQLSecretCredentials

load_dotenv(
    dotenv_path=f"{pathlib.Path(__file__).parent.resolve()}/../../.env-dev"
)


class TestDbManager(AbstractDbManager):
    def __init__(self, db_connector: DbConnector):
        super().__init__(db_connector)

        self._test_messages: Table = super().meta().tables['test_messages']

    @property
    def test_messages_table(self) -> Table:
        return self._test_messages


@pytest.fixture(scope='session')
def db_connector() -> DbConnector:
    return DbConnector(PostgreSQLSecretCredentials())


@pytest.fixture(scope='session')
def db_manager(db_connector) -> TestDbManager:
    return TestDbManager(db_connector)


@pytest.fixture()
def test_sqs_queue_url() -> str:
    return os.getenv("TEST_SQS_QUEUE_URL")