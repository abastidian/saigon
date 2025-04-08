from typing import Dict, Protocol, Union, Iterable, Type, Generic

import boto3
from mypy_boto3_sqs.client import SQSClient

import sqlalchemy

from saigon.orm.connection import DbConnector
from saigon.model import ModelTypeDef


class SqlStatementBuilder(Protocol[ModelTypeDef]):
    def prepare(self, message_type: Type[ModelTypeDef]) -> sqlalchemy.Executable:
        ...

    def get_statement_params(self, message: ModelTypeDef) -> Union[Dict, Iterable]:
        ...


class SqsToRdsForwarder(Generic[ModelTypeDef]):

    def __init__(
            self,
            message_type: Type[ModelTypeDef],
            sqs_queue_url: str,
            db_connector: DbConnector,
            sql_statement_builder: SqlStatementBuilder
    ):
        self._sqs_client: SQSClient = boto3.client('sqs')
        self._sqs_queue_url = sqs_queue_url
        self._message_type = message_type
        self._db_connector = db_connector
        self._sql_statement_builder = sql_statement_builder
        self._prepared_statement = self._sql_statement_builder.prepare(message_type)

    def forward_message(self, message_body_json: str):
        message_body = self._message_type.model_validate_json(
            message_body_json
        )
        statement_params = self._sql_statement_builder.get_statement_params(message_body)
        self._db_connector.execute(
            self._prepared_statement,
            parameters=statement_params
        )

    def forward(self, **kwargs):
        receive_result = self._sqs_client.receive_message(
            QueueUrl=self._sqs_queue_url,
            **kwargs
        )
        for message in receive_result.get('Messages', []):
            self.forward_message(message['Body'])
