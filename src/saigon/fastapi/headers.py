import uuid
import base64
from typing import Dict, Union, Optional, Self, Annotated

from pydantic import BaseModel, Field, field_serializer, field_validator
from fastapi import Header

AWS_COGNITO_IAM_AUTH_PROVIDER_HEADER_NAME = 'X-Cognito-AuthProvider'
AWS_API_REQUEST_ID_HEADER_NAME = 'X-Api-RequestId'

__all__ = [
    'RequestContext',
    'AWS_COGNITO_IAM_AUTH_PROVIDER_HEADER_NAME',
    'AWS_API_REQUEST_ID_HEADER_NAME',
    'get_user_pool_identity_from_iam_auth_provider',
    'get_api_request_id',
    'iam_auth_provider_header',
    'api_request_id_header'
]


def random_request_id() -> str:
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode()


def get_api_request_id(
    api_request_id: Optional[str] = Header(alias=AWS_API_REQUEST_ID_HEADER_NAME, default=None)
) -> str:
    # Expected Format is Ic5tLgChjoEEM1g=
    return api_request_id if api_request_id else random_request_id()


def get_user_pool_identity_from_iam_auth_provider(
        iam_auth_provider: str = Header(alias=AWS_COGNITO_IAM_AUTH_PROVIDER_HEADER_NAME)
) -> uuid.UUID:
    """
    Expected format:
    cognito-idp.${REGION}.amazonaws.com/eu-west-1_qQtoklJhb,\
    cognito-idp.${REGION}.amazonaws.com/eu-west-1_qQtoklJhb:CognitoSignIn:${USER_POOL_IDENTITY}
    """
    return uuid.UUID(iam_auth_provider.rsplit(':', maxsplit=1)[-1])


def iam_auth_provider_header(iam_auth_provider: Union[str, uuid.UUID]) -> Dict:
    return {
        AWS_COGNITO_IAM_AUTH_PROVIDER_HEADER_NAME: f"{iam_auth_provider}"
    }


def api_request_id_header(request_id: str) -> Dict:
    return {
        AWS_API_REQUEST_ID_HEADER_NAME: f"{request_id}"
    }


class RequestContext(BaseModel):
    identity_id: Annotated[
        uuid.UUID,
        Header(alias=AWS_COGNITO_IAM_AUTH_PROVIDER_HEADER_NAME)
    ] = Field(
        serialization_alias=AWS_COGNITO_IAM_AUTH_PROVIDER_HEADER_NAME,
        frozen=True
    )
    request_id: Annotated[
        Optional[str],
        Header(alias=AWS_API_REQUEST_ID_HEADER_NAME)
    ] = Field(
        random_request_id(),
        serialization_alias=AWS_API_REQUEST_ID_HEADER_NAME,
        frozen=True
    )

    @property
    def headers(self) -> dict:
        return self.model_dump(by_alias=True)

    @classmethod
    def from_identity_id(cls, identity_id: uuid.UUID) -> Self:
        return cls(
            identity_id=identity_id, request_id=random_request_id()
        )

    @field_serializer('identity_id')
    @classmethod
    def serialize_identity_id(cls, identity_id: uuid.UUID, _):
        return str(identity_id)

    @field_validator('identity_id', mode='before')
    @classmethod
    def validate_identity_id(cls, identity_id: str | uuid.UUID):
        return (
            identity_id if isinstance(identity_id, uuid.UUID)
            else get_user_pool_identity_from_iam_auth_provider(identity_id)
        )
