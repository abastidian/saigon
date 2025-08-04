from typing import Type, Optional, override

import boto3
from mypy_boto3_secretsmanager.client import SecretsManagerClient

from pydantic import BaseModel

from ..interface import SecretVault
from ..orm.config import *

__all__ = [
    'AwsSecretVault',
    'AwsBaseDbEnv',
    'get_secret_as_model'
]


class AwsSecretVault(SecretVault):
    """
    Concrete implementation of `SecretVault` that uses boto3 SecretsManager
    """
    def __init__(
            self, secrets_client: Optional[SecretsManagerClient] = None
    ):
        self._secrets_client = (
            secrets_client if secrets_client
            else boto3.client('secretsmanager')
        )

    @override
    def get_secret[SecretModel: BaseModel](
            self,
            secret_model: Type[SecretModel],
            secret_key: str
    ) -> SecretModel:
        return get_secret_as_model(
            secret_model, secret_key, self._secrets_client
        )


class AwsBaseDbEnv(BaseDbEnv):
    """
    Subclass of `BaseDbEnv` that provides `AwsSecretVault` as provider to access
    the DB secret.
    """
    def __init__(
            self,
            var_prefix: str,
            credentials_type: Type[DbCredentials] = PostgreSQLCredentials,
            **kwargs
    ):
        super().__init__(
            var_prefix,
            credentials_type,
            AwsSecretVault(),
            **kwargs
        )


def get_secret_as_model[SecretModel: BaseModel](
        model_type: Type[SecretModel],
        secret_name: str,
        secrets_client: Optional[SecretsManagerClient] = None
) -> SecretModel:
    """Retrieves a secret from AWS Secrets Manager and deserializes it into a Pydantic model.

    This function fetches the secret string from Secrets Manager and then uses
    the provided Pydantic `model_type` to parse the JSON string into a model instance.

    Args:
        model_type (Type[ModelTypeDef]): The Pydantic model class to deserialize the secret into.
        secret_name (str): The name or ARN of the secret to retrieve.
        secrets_client (Optional[SecretsManagerClient]): An optional Boto3 Secrets Manager client.
            If None, a new client will be created. Defaults to None.

    Returns:
        ModelTypeDef: An instance of the specified Pydantic model populated with the secret's data.
    """
    if secrets_client is None:
        secrets_client: SecretsManagerClient = boto3.client('secretsmanager')

    secret_response = secrets_client.get_secret_value(
        SecretId=secret_name
    )
    return model_type.model_validate_json(
        secret_response['SecretString']
    )
