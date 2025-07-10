import abc
import os
from typing import Optional, List, Type
from functools import cached_property

import boto3
from mypy_boto3_secretsmanager import SecretsManagerClient

from pydantic import BaseModel

from ..utils import Environment

__all__ = [
    'DbSecretCredentials',
    'PostgreSQLSecretCredentials',
    'MySQLSecretCredentials',
    'BaseDbEnv'
]


class DbSecretCredentials(abc.ABC, BaseModel):
    """
    Abstract base class for database secret credentials.

    Defines the common attributes and abstract methods for various database
    types, ensuring a consistent interface for accessing connection details.

    Attributes:
        endpoint (str): The database server's hostname or IP address.
            Defaults to '127.0.0.1'.
        port (int): The port number for the database connection. Defaults to 1024.
        database (str): The name of the database. Defaults to 'test-db'.
        username (str): The username for database access. Defaults to 'test-user'.
        password (str): The password for the database user. Defaults to 'test-pass'.
    """
    endpoint: str = '127.0.0.1'
    port: int = 1024
    database: str = 'test-db'
    username: str = 'test-user'
    password: str = 'test-pass'

    @property
    def host_url(self) -> str:
        """
        Constructs the host URL (endpoint:port) for the database.

        Returns:
            str: The host URL, e.g., "127.0.0.1:1024".
        """
        return f"{self.endpoint}:{self.port}"

    @property
    @abc.abstractmethod
    def db_url(self) -> str:
        """
        Abstract method to construct the full database connection URL.

        This method must be implemented by concrete subclasses to provide
        the specific URL format for their respective database types.

        Raises:
            NotImplementedError: If the method is not implemented by a subclass.

        Returns:
            str: The full database connection URL.
        """
        raise NotImplementedError


class PostgreSQLSecretCredentials(DbSecretCredentials):
    """
    Concrete implementation of DbSecretCredentials for PostgreSQL databases.

    Adds PostgreSQL-specific attributes like `ssl_mode` and provides the
    correct `db_url` format for PostgreSQL connections.

    Attributes:
        port (int): The default PostgreSQL port. Defaults to 5432.
        ssl_mode (str): The SSL mode for the PostgreSQL connection. Defaults to 'prefer'.

    Example::

        pg_creds = PostgreSQLSecretCredentials(
            endpoint="my-pg-server",
            database="mydb",
            username="pguser",
            password="pgpass",
            port=5433,
            ssl_mode="require"
        )
        print(pg_creds.db_url)
        # Expected Output: postgresql+psycopg://pguser:pgpass@my-pg-server:5433/mydb?sslmode=require
    """
    port: int = 5432
    ssl_mode: str = 'prefer'

    @property
    def db_url(self) -> str:
        """Constructs the PostgreSQL database connection URL.

        Returns:
            str: The full PostgreSQL connection URL, including SSL mode.
        """
        return (
            f"postgresql+psycopg://"
            f"{self.username}:{self.password}@{self.host_url}/{self.database}"
            f"?sslmode={self.ssl_mode}"
        )


class MySQLSecretCredentials(DbSecretCredentials):
    """
    Concrete implementation of DbSecretCredentials for MySQL databases.

    Provides the correct `db_url` format for MySQL connections.

    Attributes:
        port (int): The default MySQL port. Defaults to 3306.

    Example::

        mysql_creds = MySQLSecretCredentials(
            endpoint="my-mysql-server",
            database="mysq_db",
            username="mysqluser",
            password="mysqlpass"
        )
        print(mysql_creds.db_url)
        # Expected Output: mysql+mysqlconnector://mysqluser:mysqlpass@my-mysql-server:3306/mysq_db
    """
    port: int = 3306

    @property
    def db_url(self) -> str:
        """
        Constructs the MySQL database connection URL.

        Returns:
            str: The full MySQL connection URL.
        """
        return (
            f"mysql+mysqlconnector://"
            f"{self.username}:{self.password}@{self.host_url}/{self.database}"
        )


class BaseDbEnv(Environment):
    """
    Manages database environment variables, optionally loading credentials
    from AWS Secrets Manager.

    This class extends the `Environment` class to specifically handle database
    connection details. It can retrieve credentials either from environment
    variables (prefixed by `var_prefix` + `_DB_`) or from a specified
    AWS Secrets Manager secret.

    Attributes:
        DATABASE_CREDENTIALS_SECRET (Optional[str]): The ARN or name of the
            AWS Secrets Manager secret containing the database credentials.
            If None, credentials are expected from environment variables.

    Examples:
        Scenario 1: Loading from environment variables::

            # Assuming environment variables are set
            # export MYAPP_DB_ENDPOINT="localhost"
            # export MYAPP_DB_PORT="5432"
            # export MYAPP_DB_DATABASE="mydata"
            # export MYAPP_DB_USERNAME="appuser"
            # export MYAPP_DB_PASSWORD="secure_password"

            class MyPostgreSqlEnv(BaseDbEnv):
                pass

            db_env = MyPostgreSqlEnv(var_prefix="MYAPP")
            print(db_env.db_credentials.db_url)
            # Expected Output: postgresql+psycopg://appuser:secure_password@localhost:5432/mydata?sslmode=prefer
            print(db_env.MYAPP_DB_USERNAME) # Direct access to loaded env var

        Scenario 2: Loading from AWS Secrets Manager::

            # Assume a secret named 'my/database/credentials' exists in AWS Secrets Manager
            # with content like:
            # {
            #   "endpoint": "db.example.com",
            #   "port": 5432,
            #   "database": "prod_db",
            #   "username": "prod_user",
            #   "password": "super_secret_password"
            # }

            class ProdDbEnv(BaseDbEnv):
                DATABASE_CREDENTIALS_SECRET: Optional[str] = "my/database/credentials"

            # Requires AWS credentials configured (e.g., via ~/.aws/credentials or env vars)
            prod_env = ProdDbEnv(var_prefix="PROD_APP")
            print(prod_env.db_credentials.db_url)
            # Expected Output: postgresql+psycopg://prod_user:super_secret_password@db.example.com:5432/prod_db?sslmode=prefer
    """
    DATABASE_CREDENTIALS_SECRET: Optional[str] = None

    def __init__(
            self,
            var_prefix: str,
            credentials_type: Type[DbSecretCredentials] = PostgreSQLSecretCredentials,
            **kwargs
    ):
        """Initializes the BaseDbEnv instance.

        Args:
            var_prefix (str): The prefix used for environment variables
                related to the database (e.g., "MYAPP" would look for MYAPP_DB_ENDPOINT).
            credentials_type (Type[DbSecretCredentials]): The type of database
                credentials to expect and load (e.g., PostgreSQLSecretCredentials,
                MySQLSecretCredentials). Defaults to PostgreSQLSecretCredentials.
            **kwargs: Additional keyword arguments to pass to the parent
                `Environment` constructor.
        """
        super().__init__(**kwargs)
        self._var_prefix = var_prefix
        self._credentials_type = credentials_type

        db_credentials = (
            self.get_credentials_from_secret() if self.DATABASE_CREDENTIALS_SECRET
            else self._db_credentials_from_vars(kwargs)
        )
        # Set the loaded credentials as attributes on self with the correct prefixed names
        self._set_db_vars_from_credentials(db_credentials)

    @property
    def db_credentials(self) -> DbSecretCredentials:
        """Provides the database credentials as an object of `credentials_type`.

        This property dynamically constructs the `DbSecretCredentials` object
        from the environment variables currently loaded into this `BaseDbEnv`
        instance.

        Returns:
            DbSecretCredentials: An instance of the configured
                `credentials_type` populated with database details.
        """
        return self._db_credentials_from_vars(
            {
                name: self.__getattr__(name)
                for name in self._db_env_vars
            }
        )

    def get_credentials_from_secret(self) -> DbSecretCredentials:
        """Retrieves database credentials from AWS Secrets Manager.

        Assumes the `DATABASE_CREDENTIALS_SECRET` attribute is set.
        The secret's value is expected to be a JSON string that can be
        parsed into the specified `credentials_type`.

        Requires AWS SDK (boto3) to be configured with appropriate permissions.

        Returns:
            DbSecretCredentials: An instance of `credentials_type` populated
                from the secret.

        Raises:
            Exception: If `DATABASE_CREDENTIALS_SECRET` is not set or secret
                retrieval fails.
        """
        if not self.DATABASE_CREDENTIALS_SECRET:
            raise ValueError(
                "DATABASE_CREDENTIALS_SECRET must be set to retrieve credentials "
                "from Secrets Manager."
            )
        secrets_client: SecretsManagerClient = boto3.client('secretsmanager')
        get_secret_response = secrets_client.get_secret_value(
            SecretId=self.DATABASE_CREDENTIALS_SECRET
        )
        return self._credentials_type.model_validate_json(
            get_secret_response['SecretString']
        )

    def _set_db_vars_from_credentials(self, credentials: DbSecretCredentials):
        """Internal method to set instance attributes from a credentials object.

        Each attribute of the `credentials` object is mapped to an instance
        attribute of this `BaseDbEnv` object, prefixed according to `_var_prefix`.
        Existing environment variables for these prefixed names take precedence.

        Args:
            credentials (DbSecretCredentials): The credentials object from which
                to populate the instance's attributes.
        """
        for cred_attr in self._credential_attrs:
            db_var = self._get_db_var(cred_attr)
            value = (
                env_value if (env_value := os.getenv(db_var))
                else getattr(credentials, cred_attr) # Use getattr for direct attribute access
            )
            setattr(self, db_var, value)

    def _db_credentials_from_vars(self, db_vars: dict) -> DbSecretCredentials:
        """Internal method to create a credentials object from a dictionary of variables.

        Args:
            db_vars (dict): A dictionary where keys are the prefixed database
                environment variable names (e.g., "MYAPP_DB_ENDPOINT") and
                values are their corresponding values.

        Returns:
            DbSecretCredentials: An instance of `credentials_type` created
                from the provided dictionary.
        """
        return self._credentials_type(
            **{
                self._get_cred_attr(name): value
                for name, value in db_vars.items() if value is not None
            }
        )

    @cached_property
    def _db_env_vars(self) -> List[str]:
        """A cached list of expected database environment variable names.

        These names are constructed using the `_var_prefix` and the
        attributes of the `credentials_type`.

        Returns:
            List[str]: A list of strings, each representing an expected
                database environment variable name (e.g., "MYAPP_DB_ENDPOINT").
        """
        return [
            f"{self._var_prefix}_DB_{name.upper()}"
            for name in self._credential_attrs
        ]

    @cached_property
    def _credential_attrs(self) -> List[str]:
        """A cached list of attribute names from the `credentials_type`.

        These are the base names of the attributes that define the
        database credentials (e.g., 'endpoint', 'port').

        Returns:
            List[str]: A list of strings, each representing an attribute name
                from the `credentials_type`.
        """
        return [
            name for name in self._credentials_type.model_fields
        ]

    def _get_db_var(self, cred_attr: str) -> str:
        """Constructs the full environment variable name for a credential attribute.

        Args:
            cred_attr (str): The name of the credential attribute (e.g., 'endpoint').

        Returns:
            str: The full environment variable name (e.g., "MYAPP_DB_ENDPOINT").
        """
        return f"{self._var_prefix}_DB_{cred_attr.upper()}"

    def _get_cred_attr(self, db_var: str) -> str:
        """Extracts the base credential attribute name from a full environment variable name.

        Args:
            db_var (str): The full environment variable name (e.g., "MYAPP_DB_ENDPOINT").

        Returns:
            str: The corresponding credential attribute name (e.g., 'endpoint').
        """
        return db_var.removeprefix(f"{self._var_prefix}_DB_").lower()
