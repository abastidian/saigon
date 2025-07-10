import logging
import time
import abc
import functools
from typing import Optional, List, Callable, Sequence, Type
from contextlib import contextmanager, AbstractContextManager
from contextvars import ContextVar

import sqlalchemy
from sqlalchemy import engine_from_config, Row, RowMapping

from pydantic import BaseModel

from ..model import (
    QueryDataParams,
    QueryDataPaginationToken,
    ModelTypeDef,
    QueryDataResult,
)
from .config import DbSecretCredentials
from .model import row_mapping_to_model_data

__all__ = [
    'DbExecutionError',
    'DbConnector',
    'AbstractDbManager',
    'transactional'
]

logger = logging.getLogger(__name__)

CONNECTION_MAX_RETRIES_DEFAULT = 5

_CONNECTION_CONTEXT_VAR = ContextVar('db-connection')


class DbExecutionError(Exception):
    """
    Custom exception raised for database execution errors.

    This exception wraps underlying SQLAlchemy exceptions to provide a
    consistent error handling mechanism within the application.
    """
    def __init__(self, *args):
        super().__init__(*args)


class DbConnector:
    """
    Provides a thin wrapper around a SQLAlchemy engine for database interactions.

    Manages the SQLAlchemy engine and provides methods for executing queries,
    fetching results, and reflecting database metadata. It also integrates
    with a context variable for managing transactional connections.
    """
    def __init__(self, credentials: DbSecretCredentials):
        """Instantiates a SQLAlchemy engine with the given database credentials.

        Args:
            credentials (DbSecretCredentials): An object containing the database
                connection details (e.g., `PostgreSQLSecretCredentials`).
        """
        self._engine_config = {
            'sqlalchemy.url': credentials.db_url
        }

        # Actually build the engine
        self._engine = None
        self.refresh_engine()

    def refresh_engine(self) -> None:
        """
        Refreshes the database connection by re-creating the SQLAlchemy engine.

        This method is useful for scenarios where connection parameters might
        change or to explicitly dispose of old connections. It relies on
        Python's garbage collection to close previous engine's connections.

        Raises:
            DbExecutionError: If there's an error during engine creation.
        """
        try:
            self._engine: sqlalchemy.engine.Engine = engine_from_config(
                configuration=self._engine_config
            )

            # Relying on garbage collection to close out the previous engine's connections and
            # prevent holding connections or memory leaks. This is done in order to allow
            # any open transactions to continue with the previous credentials until completion.
            # If this becomes problematic, we will need to schedule a job to `dispose` of the
            # previous engine after all requests that are using it are finished.
        except sqlalchemy.exc.SQLAlchemyError as err:
            raise DbExecutionError(str(err)) from err

    @property
    def engine(self) -> sqlalchemy.engine.Engine:
        """
        Obtains a reference to the underlying SQLAlchemy engine.

        Returns:
            sqlalchemy.engine.Engine: The SQLAlchemy engine instance.
        """
        return self._engine

    @property
    def connection(self) -> Optional[sqlalchemy.Connection]:
        """
        Retrieves the current database connection from the context variable.

        This property allows access to a connection that might be bound
        to a transaction via `transaction_context` or `transactional` decorator.

        Returns:
            Optional[sqlalchemy.Connection]: The current connection if set, otherwise None.
        """
        return _CONNECTION_CONTEXT_VAR.get(None)

    def fetch_one(
        self,
        selectable: sqlalchemy.Executable,
        **kwargs,
    ) -> Optional[sqlalchemy.engine.result.Row]:
        """
        Executes the given SQLAlchemy selectable and returns the first row.

        Args:
            selectable (sqlalchemy.Executable): Any object considered "selectable"
                by SQLAlchemy (e.g., a `sqlalchemy.Select` statement).
            **kwargs: Additional keyword arguments to pass to the `execute` method,
                such as `parameters` for bind values.

        Returns:
            Optional[sqlalchemy.engine.result.Row]: The first row of the result set,
                or None if no rows are found.
        """
        return self.execute(selectable, **kwargs).first()

    def fetch_all(
            self,
            selectable: sqlalchemy.Executable,
            **kwargs
    ) -> Sequence[sqlalchemy.engine.result.Row]:
        """
        Executes the given SQLAlchemy selectable and returns all rows.

        An empty list is returned if no rows match the selection.

        Args:
            selectable (sqlalchemy.Executable): Any object considered "selectable"
                by SQLAlchemy (e.g., a `sqlalchemy.Select` statement).
            **kwargs: Additional keyword arguments to pass to the `execute` method,
                such as `parameters` for bind values.

        Returns:
            Sequence[sqlalchemy.engine.result.Row]: A sequence of all rows from the
                result set.
        """
        return self.execute(selectable, **kwargs).fetchall()

    def execute(
            self,
            obj: sqlalchemy.Executable,
            **kwargs
    ) -> sqlalchemy.engine.ResultProxy:
        """
        Executes the given SQLAlchemy callable object or literal SQL statement.

        This method will acquire a connection from the pool, execute the given
        statement, and return the result. If a connection is already bound to
        the current context (e.g., by a transaction), that connection will be used.

        Args:
            obj (sqlalchemy.Executable): Statement to execute. See SQLAlchemy's docs
                for the full list of supported types. For literal statements,
                prepare this value with `sqlalchemy.text('SELECT ... FROM')`.
            **kwargs: Keyword arguments for the execution, such as `parameters`
                (Union[Dict, Iterable]) for bind parameter values.

        Returns:
            sqlalchemy.ResultProxy: The statement result.

        Raises:
            DbExecutionError: All SQLAlchemy exceptions are caught and re-raised
                as `DbExecutionError`.
        """
        if (connection := self.connection) is None:
            # SQLAlchemy uses an implicit connection here with close_with_result=True.
            # Exhausting the ResultProxy will close the connection.
            with self.engine.begin() as conn:
                return conn.execute(obj, **kwargs)

        try:
            return connection.execute(obj, **kwargs)

        except sqlalchemy.exc.SQLAlchemyError as err:
            raise DbExecutionError(str(err)) from err

    def reflect(self, retries: int) -> sqlalchemy.MetaData:
        """
        Reflects all database objects (tables, etc.) into a SQLAlchemy MetaData object.

        This method is typically called at service startup. It includes a retry
        mechanism to handle transient connection issues or timing problems
        between service and database startup.

        Args:
            retries (int): The number of retries before raising an exception.
                Each retry uses an exponential back-off.

        Returns:
            sqlalchemy.MetaData: A `MetaData` object containing the reflected
                database schema.

        Raises:
            DbExecutionError: If reflection fails after all retries.
        """
        meta = sqlalchemy.MetaData()
        for attempt in range(retries):
            try:
                meta.reflect(bind=self.engine)
                return meta
            except sqlalchemy.exc.OperationalError as err:
                nsecs = 2 ** attempt
                logger.warning(f"{err} retrying in {nsecs} seconds")
                time.sleep(nsecs)
            except sqlalchemy.exc.SQLAlchemyError as err:
                raise DbExecutionError(err) from err

        raise DbExecutionError(f"reflection failed after retries={retries}")


class AbstractDbManager(abc.ABC):
    """
    Provides a uniform interface for interacting with a service's database model.

    This abstract class encapsulates common database operations such as
    transaction management, pagination, and entity retrieval/deletion,
    working with a `DbConnector` instance.
    """

    __meta = None

    def __init__(
            self,
            db_connector: DbConnector,
            retries: Optional[int] = CONNECTION_MAX_RETRIES_DEFAULT
    ) -> None:
        """Initializes the AbstractDbManager.

        Performs database reflection upon initialization if it hasn't been done already.

        Args:
            db_connector (DbConnector): An instance of `DbConnector` to use for
                database interactions.
            retries (Optional[int]): The number of retries for database reflection
                at startup. Defaults to `CONNECTION_MAX_RETRIES_DEFAULT`.
        """
        self.db_connector = db_connector
        self.__reflect(retries)

    @classmethod
    def meta(cls) -> sqlalchemy.MetaData:
        """
        Returns the SQLAlchemy MetaData object containing reflected database schema.

        This is a class method because the MetaData is typically shared across
        all instances of a DbManager subclass.

        Returns:
            sqlalchemy.MetaData: The reflected database metadata.
        """
        return cls.__meta

    def transaction(self) -> AbstractContextManager:
        """
        Returns a context manager for managing a database transaction.

        Usage with `with self.transaction():` ensures that all database
        operations within the block run within a single transaction.

        Returns:
            AbstractContextManager: A context manager that yields a SQLAlchemy
                connection for transactional operations.
        """
        return transaction_context(self.db_connector)

    def paginate[QuerySelection, ModelType: BaseModel](
            self,
            query_selection_type: Type[QuerySelection],
            query_params: QueryDataParams[QuerySelection],
            build_select: Callable[[Optional[QuerySelection]], sqlalchemy.Select],
            single_row_to_data: Optional[Callable[[RowMapping, ...], ModelType]] = None,
            multirow_to_data: Optional[Callable[[Sequence[Row], ...], List[ModelType]]] = None,
            **kwargs
    ) -> QueryDataResult[ModelType]:
        """
        Paginates database queries based on provided parameters and converts results to models.

        This method handles the logic for applying limits and offsets, decoding
        pagination tokens, executing the query, and converting the raw database
        rows into Pydantic models.

        Args:
            query_selection_type (Type[QuerySelection]): The Pydantic model type
                representing the query selection criteria.
            query_params (QueryDataParams[QuerySelection]): An object containing
                pagination and query selection parameters.
            build_select (Callable[[Optional[QuerySelection]], sqlalchemy.Select]):
                A callable that takes an optional `QuerySelection` object and
                returns a SQLAlchemy `Select` statement. This function defines
                the base query.
            single_row_to_data (Optional[Callable[[RowMapping, ...], ModelType]]):
                A callable that converts a single `RowMapping` (from SQLAlchemy)
                into an instance of `ModelType`. Required if `multirow_to_data` is None.
            multirow_to_data (Optional[Callable[[Sequence[Row], ...], List[ModelType]]]):
                A callable that converts a sequence of `Row` objects into a list
                of `ModelType` instances. Required if `single_row_to_data` is None.
            **kwargs: Additional keyword arguments to pass to the `single_row_to_data`
                or `multirow_to_data` conversion functions.

        Returns:
            QueryDataResult[ModelType]: An object containing the fetched data
                (list of `ModelType` instances) and an updated pagination token
                (if more data is available).

        Raises:
            ValueError: If neither `single_row_to_data` nor `multirow_to_data` is provided.

        Example:

        Consider a `User` model and a `UserQuery` for selection::

            from pydantic import BaseModel
            from sqlalchemy import Table, Column, Integer, String, MetaData, select

            # Assume 'users_table' is reflected via manager.meta()
            metadata = MetaData()
            users_table = Table(
                "users", metadata,
                Column("id", Integer, primary_key=True),
                Column("name", String),
                Column("email", String)
            )

            class User(BaseModel):
                id: int
                name: str
                email: str

            class UserQuery(BaseModel):
                name_starts_with: Optional[str] = None

            def build_user_select(query_selection: Optional[UserQuery]) -> sqlalchemy.Select:
                stmt = select(users_table)
                if query_selection and query_selection.name_starts_with:
                    stmt = stmt.where(users_table.c.name.startswith(query_selection.name_starts_with))
                return stmt

            def row_to_user_model(row_mapping: RowMapping) -> User:
                return User(id=row_mapping['id'], name=row_mapping['name'], email=row_mapping['email'])

            # Assuming db_manager is an instance of AbstractDbManager
            # db_manager = MyDbManager(db_connector=DbConnector(credentials))

            # Query for users with name starting with 'J', limit 2
            query_params = QueryDataParams[UserQuery](
                query_selection=UserQuery(name_starts_with="J"),
                max_count=2
            )
            result = db_manager.paginate(
                query_selection_type=UserQuery,
                query_params=query_params,
                build_select=build_user_select,
                single_row_to_data=row_to_user_model
            )

            print(f"Fetched users: {[u.name for u in result.data]}")
            if result.pagination_token:
                print(f"Next token available: {result.pagination_token.query_id}")

            # To fetch next page:
            # next_query_params = QueryDataParams[UserQuery](
            #     pagination_token=result.pagination_token,
            #     max_count=2
            # )
            # next_result = db_manager.paginate(
            #     query_selection_type=UserQuery,
            #     query_params=next_query_params,
            #     build_select=build_user_select,
            #     single_row_to_data=row_to_user_model
            # )
            # print(f"Fetched next users: {[u.name for u in next_result.data]}")
        """
        if single_row_to_data is None and multirow_to_data is None:
            raise ValueError('A converter from row to model data must be provided')

        if (pagination_token := query_params.pagination_token) and pagination_token.query_id:
            query_selection = query_params.decode_query_selection(
                query_selection_type
            )
        else:
            query_selection = query_params.query_selection

        select_statement = build_select(query_selection)

        # Incorporate limit and offset
        if query_params.has_max_count():
            select_statement = select_statement.limit(query_params.max_count)

        if query_offset := (
            pagination_token.next_token_as_offset if pagination_token else None
        ):
            select_statement = select_statement.offset(query_offset)

        # Run tx
        row_seq = self.db_connector.fetch_all(select_statement)
        row_count = len(row_seq)
        if single_row_to_data:
            fetched_items = []
            for row in row_seq:
                fetched_items.append(
                    single_row_to_data(row._mapping, **kwargs)
                )
        else:
            fetched_items = multirow_to_data(row_seq, **kwargs)

        # Return a pagination token based on query and result
        if row_count == query_params.max_count:
            if pagination_token:
                pagination_token.next_token_as_offset = query_offset + row_count
            else:
                # codify the custom selection
                pagination_token = QueryDataPaginationToken.from_offset(
                    QueryDataParams(query_selection=query_selection).encode_query_selection(),
                    query_params.max_count
                )
        else:
            pagination_token = None

        return QueryDataResult(
            data=fetched_items, pagination_token=pagination_token
        )

    def get_entity(
            self, model_type: Type[ModelTypeDef], select_statement: sqlalchemy.Select
    ) -> Optional[ModelTypeDef]:
        """
        Fetches a single entity from the database and converts it to a Pydantic model.

        Args:
            model_type (Type[ModelTypeDef]): The Pydantic model type to convert
                the fetched row into.
            select_statement (sqlalchemy.Select): The SQLAlchemy `Select` statement
                to execute, expected to return at most one row.

        Returns:
            Optional[ModelTypeDef]: An instance of `model_type` if a row is found,
                otherwise None.
        """
        row_entity = self.db_connector.fetch_one(select_statement)
        return (
            row_mapping_to_model_data(model_type, row_entity._mapping) if row_entity
            else None
        )

    def delete_entity(self, delete_statement: sqlalchemy.Delete):
        """
        Executes a SQLAlchemy Delete statement to remove entities from the database.

        Args:
            delete_statement (sqlalchemy.Delete): The SQLAlchemy `Delete` statement
                to execute.
        """
        self.db_connector.execute(delete_statement)

    def __reflect(self, retries: int) -> sqlalchemy.MetaData:
        """
        Internal method to perform database reflection.

        This method ensures that the `__meta` class variable is populated with
        the reflected database schema. It's designed to be called once per
        application lifecycle.

        Args:
            retries (int): The number of retries for reflection.

        Returns:
            sqlalchemy.MetaData: The reflected database metadata.
        """
        # NOTE: this assumes that you do not change the table definition without
        # restarting the service. This should be a safe assumption since we will need
        # to restart the service in order to have it consume table changes, but it
        # is something we need to keep in mind.
        if self.__class__.__meta is None:
            self.__class__.__meta = self.db_connector.reflect(retries)

        return self.__class__.__meta


@contextmanager
def transaction_context(db_connector: DbConnector) -> sqlalchemy.Connection:
    """
    A context manager for managing a database transaction.

    This context manager acquires a connection from the `DbConnector`'s engine,
    starts a transaction, and yields the connection. The transaction is
    committed upon successful exit from the `with` block or rolled back
    if an exception occurs. It also binds the connection to a `ContextVar`
    for access by other methods within the same context.

    Args:
        db_connector (DbConnector): The database connector instance.

    Yields:
        sqlalchemy.Connection: The active SQLAlchemy connection within the transaction.

    Raises:
        DbExecutionError: If any SQLAlchemy error occurs during the transaction.

    Example::

        # Assuming db_connector is an instance of DbConnector
        # db_connector = DbConnector(credentials)

        try:
            with transaction_context(db_connector) as conn:
                # Execute multiple statements within the same transaction
                conn.execute(sqlalchemy.text("INSERT INTO users (name) VALUES ('Alice')"))
                conn.execute(sqlalchemy.text("UPDATE products SET price = 100 WHERE id = 1"))
                # If an error occurs here, both operations will be rolled back
            print("Transaction committed successfully.")
        except DbExecutionError as e:
            print(f"Transaction failed: {e}")
    """
    previous_token = None
    try:
        with db_connector.engine.begin() as connection:
            previous_token = _CONNECTION_CONTEXT_VAR.set(connection)
            yield connection
    except sqlalchemy.exc.SQLAlchemyError as err:
        raise DbExecutionError(str(err)) from err
    finally:
        if previous_token:
            _CONNECTION_CONTEXT_VAR.reset(previous_token)


def transactional(func: Callable) -> Callable:
    """
    A decorator that ensures a method executes within a database transaction.

    If the decorated method is called and a database connection is already
    bound to the current context (meaning it's already within a transaction),
    the method will use that existing connection. Otherwise, it will create
    a new transaction context using `transaction_context` for the duration
    of the method's execution.

    Args:
        func (Callable): The method to be decorated. This method is expected
            to be an instance method of a class that inherits from `AbstractDbManager`,
            and its first argument should be `self` (the manager instance).

    Returns:
        Callable: The wrapped function, which now executes within a transaction.

    Example::

        class MyManager(AbstractDbManager):
            def __init__(self, db_connector: DbConnector):
                super().__init__(db_connector)
                # Assume 'users_table' is reflected and available via self.meta()

            @transactional
            def add_user_and_log(self, user_name: str, log_message: str):
                # Both operations will be part of the same transaction
                insert_stmt = sqlalchemy.text("INSERT INTO users (name) VALUES (:name)").bindparams(name=user_name)
                self.db_connector.execute(insert_stmt)

                log_stmt = sqlalchemy.text("INSERT INTO logs (message) VALUES (:message)").bindparams(message=log_message)
                self.db_connector.execute(log_stmt)
                print(f"User '{user_name}' added and log '{log_message}' recorded.")

        # Usage:
        # db_connector = DbConnector(credentials)
        # manager = MyManager(db_connector)
        # manager.add_user_and_log("Bob", "New user registered")
        # If any error occurs during add_user_and_log, both inserts are rolled back.
    """

    @functools.wraps(func)
    def wrapped(manager: AbstractDbManager, *args, **kwargs):
        if manager.db_connector.connection:
            # If already in a transaction, just execute the function
            return func(manager, *args, **kwargs)

        # Otherwise, create a new transaction context
        with transaction_context(manager.db_connector):
            return func(manager, *args, **kwargs)

    return wrapped
