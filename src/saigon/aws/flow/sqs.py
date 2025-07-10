from typing import Dict, Protocol, Union, Iterable, Type, Generic

from pydantic import BaseModel

import boto3
from mypy_boto3_sqs.client import SQSClient

import sqlalchemy

from ...orm.connection import DbConnector


class SqlStatementBuilder[ModelTypeDef: BaseModel](Protocol):
    """
    A protocol defining the interface for building SQLAlchemy SQL statements
    and extracting parameters from a message.

    This protocol ensures that any class implementing it can prepare an
    executable SQLAlchemy statement based on a message type and then extract
    the necessary parameters from a specific message instance for that statement.

    TypeVar `ModelTypeDef` is bound to `saigon.model.ModelTypeDef`, implying
    that the messages processed by this builder are Pydantic-like models.
    """
    def prepare(self, message_type: Type[ModelTypeDef]) -> sqlalchemy.Executable:
        """
        Prepares an executable SQLAlchemy statement for a given message type.

        This method should define the SQL operation (e.g., INSERT, UPDATE)
        and specify how it interacts with the database schema, often based
        on the structure of `message_type`. The returned `sqlalchemy.Executable`
        object can then be executed by a SQLAlchemy connection.

        Args:
            message_type (Type[ModelTypeDef]): The Pydantic model type representing
                the structure of the SQS message.

        Returns:
            sqlalchemy.Executable: An executable SQLAlchemy statement object.
        """
        ...

    def get_statement_params(self, message: ModelTypeDef) -> Union[Dict, Iterable]:
        """
        Extracts parameters from a message for use with a prepared SQL statement.

        This method takes an instance of a message and transforms it into a format
        suitable for parameter binding in a SQLAlchemy statement (e.g., a dictionary
        for `INSERT` or `UPDATE` statements, or a list of dictionaries for `INSERT`
        with multiple rows).

        Args:
            message (ModelTypeDef): An instance of the Pydantic model representing
                an SQS message.

        Returns:
            Union[Dict, Iterable]: A dictionary or an iterable of dictionaries
                containing the parameters to be bound to the SQL statement.
        """
        ...


class SqsToRdsForwarder[ModelTypeDef: BaseModel]():
    """
    A generic class to forward messages from an SQS queue to an RDS database.

    This class continuously polls an SQS queue for messages of a specific type,
    deserializes them, and then uses a `SqlStatementBuilder` to convert them
    into SQL statements that are executed against an RDS database via a `DbConnector`.

    TypeVar `ModelTypeDef` is bound to `saigon.model.ModelTypeDef`.
    """

    def __init__(
            self,
            message_type: Type[ModelTypeDef],
            sqs_queue_url: str,
            db_connector: DbConnector,
            sql_statement_builder: SqlStatementBuilder[ModelTypeDef]
    ):
        """
        Initializes the SqsToRdsForwarder.

        Args:
            message_type (Type[ModelTypeDef]): The Pydantic model type that
                represents the structure of messages expected in the SQS queue.
            sqs_queue_url (str): The URL of the SQS queue to read messages from.
            db_connector (DbConnector): An instance of `DbConnector` for database interactions.
            sql_statement_builder (SqlStatementBuilder[ModelTypeDef]): An instance of a class
                implementing `SqlStatementBuilder` to generate SQL statements.
        """
        self._sqs_client: SQSClient = boto3.client('sqs')
        self._sqs_queue_url = sqs_queue_url
        self._message_type = message_type
        self._db_connector = db_connector
        self._sql_statement_builder = sql_statement_builder
        # Prepare the statement once during initialization for efficiency
        self._prepared_statement = self._sql_statement_builder.prepare(message_type)

    def forward_message(self, message_body_json: str):
        """
        Processes a single SQS message by deserializing it and inserting it into RDS.

        This method is responsible for taking the raw JSON body of an SQS message,
        validating it against the `message_type`, extracting parameters using the
        `sql_statement_builder`, and then executing the prepared SQL statement
        with those parameters against the database.

        Args:
            message_body_json (str): The JSON string content of the SQS message body.
        """
        message_body = self._message_type.model_validate_json(
            message_body_json
        )
        statement_params = self._sql_statement_builder.get_statement_params(message_body)
        self._db_connector.execute(
            self._prepared_statement,
            parameters=statement_params
        )

    def forward(self, **kwargs):
        """
        Receives messages from the SQS queue and forwards them to RDS.

        This method performs a `receive_message` call to SQS. For each message
        received, it calls `forward_message` to process it. Additional keyword
        arguments can be passed to customize the SQS `receive_message` call
        (e.g., `MaxNumberOfMessages`, `WaitTimeSeconds`).

        Args:
            **kwargs: Arbitrary keyword arguments to be passed directly to the
                `SQSClient.receive_message` method (e.g., `MaxNumberOfMessages`,
                `VisibilityTimeout`, `WaitTimeSeconds`, `AttributeNames`).
        """
        receive_result = self._sqs_client.receive_message(
            QueueUrl=self._sqs_queue_url,
            **kwargs
        )
        for message in receive_result.get('Messages', []):
            # In a real-world scenario, successful processing should be followed
            # by deleting the message from the queue using its ReceiptHandle.
            # This example focuses solely on forwarding to RDS.
            self.forward_message(message['Body'])