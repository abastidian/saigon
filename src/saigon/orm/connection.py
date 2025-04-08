from typing import Optional, List, Callable, Sequence, Type
import base64
import json
import logging
import time
import abc
import functools
from contextlib import contextmanager, AbstractContextManager
from contextvars import ContextVar

import sqlalchemy
from sqlalchemy import engine_from_config, Row, RowMapping

from pydantic_core import to_jsonable_python

from saigon.model import (
    CustomQuerySelection,
    QueryDataParams,
    QueryDataPaginationToken,
    ModelTypeDef,
    QueryDataResult,
)
from saigon.orm.config import DbSecretCredentials
from saigon.orm.model import row_mapping_to_model_data

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
    def __init__(self, *args):
        super().__init__(*args)


class DbConnector:

    """
    Provide a thin wrapper around a SQLAlchemy engine.
    """
    def __init__(self, credentials: DbSecretCredentials):
        """
        Instantiate an engine with the given configuration.
        """
        self._engine_config = {
            'sqlalchemy.url': credentials.db_url
        }

        # actually build the engine
        self._engine = None
        self.refresh_engine()

    def refresh_engine(self) -> None:
        """Refresh the Database Connection with an updated set of credentials."""
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
        """sqlalchemy.engine.Engine: Obtain a reference to the underlying SQLAlchemy engine."""
        return self._engine

    @property
    def connection(self) -> Optional[sqlalchemy.Connection]:
        return _CONNECTION_CONTEXT_VAR.get(None)

    def fetch_one(
        self,
        selectable: sqlalchemy.Executable,
        **kwargs,
    ) -> Optional[sqlalchemy.engine.result.Row]:
        """
        Execute the given SQLAlchemy selectable and return the first row.

        Arguments:
            selectable: Any object considered "selectable" by SQLAlchemy.
        """

        return self.execute(selectable, **kwargs).first()

    def fetch_all(
            self,
            selectable: sqlalchemy.Executable,
            **kwargs
    ) -> Sequence[sqlalchemy.engine.result.Row]:
        """
        Execute the given SQLAlchemy selectable and return all the rows.

        An empty list is returned if no rows match the selection.

        Arguments:
            selectable: Any object considered "selectable" by SQLAlchemy.
        """
        return self.execute(selectable, **kwargs).fetchall()

    def execute(
            self,
            obj: sqlalchemy.Executable,
            **kwargs
    ) -> sqlalchemy.engine.ResultProxy:
        """
        Execute the given SQLAlchemy callable object or literal SQL statement.

        This method will acquire a connection from the pool, execute the given
        statement and return the result

       Arguments:
            obj: Statement to execute. See SQLAlchemy's docs for the full list of supported types.
                For literal statements prepare this value with
                ``sqlalchemy.text('SELECT ... FROM')``.
        Keyword Arguments:
            parameters (Union[Dict, Iterable]): Bind parameter values

        Returns:
            sqlalchemy.ResultProxy: Statement result.

        Raises:
            DbExecutionError: All SQLAlchemy exceptions are caught and translated.
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
        Reflect all database objects.

        Arguments:
            retries: Number of retries before raising an exception. This method is
            typically called at startup. Use this argument to handle timing issues
            between service and database startup.
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
    """

    __meta = None

    def __init__(
            self,
            db_connector: DbConnector,
            retries: Optional[int] = CONNECTION_MAX_RETRIES_DEFAULT
    ) -> None:
        self.db_connector = db_connector
        self.__reflect(retries)

    @classmethod
    def meta(cls) -> sqlalchemy.MetaData:
        return cls.__meta

    def transaction(self) -> AbstractContextManager:
        return transaction_context(self.db_connector)

    def paginate(
            self,
            query_selection_type: Type[CustomQuerySelection],
            query_params: QueryDataParams[CustomQuerySelection],
            build_select: Callable[[Optional[CustomQuerySelection]], sqlalchemy.Select],
            single_row_to_data: Optional[Callable[[RowMapping, ...], ModelTypeDef]] = None,
            multirow_to_data: Optional[Callable[[Sequence[Row], ...], List[ModelTypeDef]]] = None,
            **kwargs
    ) -> QueryDataResult[ModelTypeDef]:
        if single_row_to_data is None and multirow_to_data is None:
            raise ValueError('A converter from row to model data must be provided')

        if (pagination_token := query_params.pagination_token) and pagination_token.query_id:
            query_selection_dict: dict = json.loads(
                base64.b64decode(pagination_token.query_id.encode()).decode()
            )
            query_selection = query_selection_type(**query_selection_dict)

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
                query_id = base64.urlsafe_b64encode(
                    json.dumps(
                        to_jsonable_python(query_selection)
                    ).encode()
                ).decode()
                pagination_token = QueryDataPaginationToken.from_offset(
                    query_id,
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
        row_entity = self.db_connector.fetch_one(select_statement)
        return (
            row_mapping_to_model_data(model_type, row_entity._mapping) if row_entity
            else None
        )

    def delete_entity(self, delete_statement: sqlalchemy.Delete):
        self.db_connector.execute(delete_statement)

    def __reflect(self, retries: int) -> sqlalchemy.MetaData:
        # NOTE: this assumes that you do not change the table definition without
        # restarting the service.  This should be a safe assumption since we will need
        # to restart the service in order to have it consume table changes, but it
        # is something we need to keep in mind.
        if self.__class__.__meta is None:
            self.__class__.__meta = self.db_connector.reflect(retries)

        return self.__class__.__meta


@contextmanager
def transaction_context(db_connector: DbConnector) -> sqlalchemy.Connection:
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
    Makes a method execute within the context of a database transaction.
    """

    @functools.wraps(func)
    def wrapped(manager: AbstractDbManager, *args, **kwargs):
        if manager.db_connector.connection:
            return func(manager, *args, **kwargs)

        with transaction_context(manager.db_connector):
            return func(manager, *args, **kwargs)

    return wrapped
