from typing import Dict, Union, Iterable, Type
import pytest

from pydantic import BaseModel
from pydantic_core import to_jsonable_python
import sqlalchemy

from saigon.aws.flow.sqs import SqsToRdsForwarder, SqlStatementBuilder


class TestMessage(BaseModel):
    id: int
    value: str


class TestInsertStatementBuilder(SqlStatementBuilder[TestMessage]):

    def __init__(self, test_message_table: sqlalchemy.Table):
        self._target_db_table = test_message_table

    def prepare(self, message_type: Type[TestMessage]) -> sqlalchemy.Executable:
        return self._target_db_table.insert()

    def get_statement_params(self, message: TestMessage) -> Union[Dict, Iterable]:
        return to_jsonable_python(message, exclude_none=True),


class TestSqsToRdsForwarder:

    @pytest.fixture()
    def sqs_forwarder(self, db_manager, test_sqs_queue_url) -> SqsToRdsForwarder:
        return SqsToRdsForwarder(
            TestMessage,
            test_sqs_queue_url,
            db_manager.db_connector,
            TestInsertStatementBuilder(
                db_manager.test_messages_table
            )
        )

    def test_forward(self, sqs_forwarder):
        sqs_forwarder.forward()






