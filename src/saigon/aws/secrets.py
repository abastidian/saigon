from typing import Type, Optional

import boto3
from mypy_boto3_secretsmanager.client import SecretsManagerClient

from ..model import ModelTypeDef

__all__ = [
    'get_secret_as_model'
]


def get_secret_as_model(
        model_type: Type[ModelTypeDef],
        secret_name: str,
        secrets_client: Optional[SecretsManagerClient] = None
) -> ModelTypeDef:
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
