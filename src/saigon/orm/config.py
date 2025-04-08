import abc
import os
from typing import Optional, List, Type
from functools import cached_property

import boto3
from mypy_boto3_secretsmanager import SecretsManagerClient

from pydantic import BaseModel

from saigon.utils import Environment

__all__ = [
    'DbSecretCredentials',
    'PostgreSQLSecretCredentials',
    'MySQLSecretCredentials',
    'BaseDbEnv'
]


class DbSecretCredentials(abc.ABC, BaseModel):
    endpoint: str = '127.0.0.1'
    port: int = 1024
    database: str = 'test-db'
    username: str = 'test-user'
    password: str = 'test-pass'

    @property
    def host_url(self) -> str:
        return f"{self.endpoint}:{self.port}"

    @property
    @abc.abstractmethod
    def db_url(self) -> str:
        raise NotImplementedError


class PostgreSQLSecretCredentials(DbSecretCredentials):
    port: int = 5432
    ssl_mode: str = 'prefer'

    @property
    def db_url(self) -> str:
        return (
            f"postgresql+psycopg://"
            f"{self.username}:{self.password}@{self.host_url}/{self.database}"
            f"?sslmode={self.ssl_mode}"
        )


class MySQLSecretCredentials(DbSecretCredentials):
    port: int = 3306

    @property
    def db_url(self) -> str:
        return (
            f"mysql+mysqlconnector://"
            f"{self.username}:{self.password}@{self.host_url}/{self.database}"
        )


class BaseDbEnv(Environment):
    DATABASE_CREDENTIALS_SECRET: Optional[str] = None

    def __init__(
            self,
            var_prefix: str,
            credentials_type: Type[DbSecretCredentials] = PostgreSQLSecretCredentials,
            **kwargs
    ):
        super().__init__(**kwargs)
        self._var_prefix = var_prefix
        self._credentials_type = credentials_type

        db_credentials = (
            self.get_credentials_from_secret() if self.DATABASE_CREDENTIALS_SECRET
            else self._db_credentials_from_vars(kwargs)
        )
        self._set_db_vars_from_credentials(db_credentials)

    @property
    def db_credentials(self) -> DbSecretCredentials:
        return self._db_credentials_from_vars(
            {
                name: self.__getattr__(name)
                for name in self._db_env_vars
            }
        )

    def get_credentials_from_secret(self) -> DbSecretCredentials:
        secrets_client: SecretsManagerClient = boto3.client('secretsmanager')
        get_secret_response = secrets_client.get_secret_value(
            SecretId=self.DATABASE_CREDENTIALS_SECRET
        )
        return self._credentials_type.model_validate_json(
            get_secret_response['SecretString']
        )

    def _set_db_vars_from_credentials(self, credentials: DbSecretCredentials):
        for cred_attr in self._credential_attrs:
            db_var = self._get_db_var(cred_attr)
            value = (
                env_value if (env_value := os.getenv(db_var))
                else credentials.__getattribute__(cred_attr)
            )
            setattr(self, db_var, value)

    def _db_credentials_from_vars(self, db_vars: dict) -> DbSecretCredentials:
        return self._credentials_type(
            **{
                self._get_cred_attr(name): value
                for name, value in db_vars.items() if value is not None
            }
        )

    @cached_property
    def _db_env_vars(self) -> List[str]:
        return [
            f"{self._var_prefix}_DB_{name.upper()}"
            for name in self._credential_attrs
        ]

    @cached_property
    def _credential_attrs(self) -> List[str]:
        return [
            name for name in self._credentials_type.model_fields
        ]

    def _get_db_var(self, cred_attr: str) -> str:
        return f"{self._var_prefix}_DB_{cred_attr.upper()}"

    def _get_cred_attr(self, db_var: str) -> str:
        return db_var.removeprefix(f"{self._var_prefix}_DB_").lower()
