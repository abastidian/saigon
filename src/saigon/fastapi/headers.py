import uuid
import base64
from typing import Dict, Union, Optional, Self, Annotated

from pydantic import BaseModel, Field, field_serializer, field_validator

from fastapi import Header
from fastapi.exceptions import RequestValidationError

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
    """Generates a random URL-safe base64 encoded UUID for use as a request ID.

    Returns:
        str: A unique, URL-safe string representing a request ID.
    """
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode()


def get_api_request_id(
    api_request_id: Optional[str] = Header(alias=AWS_API_REQUEST_ID_HEADER_NAME, default=None)
) -> str:
    """Retrieves the API request ID from the 'X-Api-RequestId' header or generates a new one.

    If the 'X-Api-RequestId' header is present, its value is used. Otherwise, a
    new random request ID is generated. The expected format for the header is
    a base64 encoded string (e.g., 'Ic5tLgChjoEEM1g=').

    Args:
        api_request_id (Optional[str]): The value of the 'X-Api-RequestId' header,
            injected by FastAPI.

    Returns:
        str: The API request ID, either from the header or a newly generated one.
    """
    # Expected Format is Ic5tLgChjoEEM1g=
    return api_request_id if api_request_id else random_request_id()


def get_user_pool_identity_from_iam_auth_provider(
        iam_auth_provider: str = Header(alias=AWS_COGNITO_IAM_AUTH_PROVIDER_HEADER_NAME)
) -> uuid.UUID:
    """Extracts the user pool identity (UUID) from the 'X-Cognito-AuthProvider' header.

    This function parses the AWS Cognito IAM Auth Provider header string to
    isolate and return the UUID representing the user's identity within
    the Cognito User Pool.

    Args:
        iam_auth_provider (str): The value of the 'X-Cognito-AuthProvider' header,
            injected by FastAPI. Expected format is
            'cognito-idp.${REGION}.amazonaws.com/${USER_POOL_ID},cognito-idp.${REGION}.amazonaws.com/${USER_POOL_ID}:CognitoSignIn:${USER_POOL_IDENTITY}'.

    Returns:
        uuid.UUID: The UUID of the user pool identity.
    """
    """
    Expected format:
    cognito-idp.${REGION}.amazonaws.com/eu-west-1_aaaaaaaaa,\
    cognito-idp.${REGION}.amazonaws.com/eu-west-1_aaaaaaaaa:CognitoSignIn:${USER_POOL_IDENTITY}
    """
    return uuid.UUID(iam_auth_provider.rsplit(':', maxsplit=1)[-1])


def iam_auth_provider_header(iam_auth_provider: Union[str, uuid.UUID]) -> Dict:
    """Constructs a dictionary representing the 'X-Cognito-IAM-AuthProvider' header.

    This utility function is useful for programmatically creating HTTP headers
    that include the Cognito IAM Auth Provider information.

    Args:
        iam_auth_provider (Union[str, uuid.UUID]): The user pool identity,
            either as a UUID object or its string representation.

    Returns:
        Dict: A dictionary with the header name as key and the formatted
            identity as value.
    """
    return {
        AWS_COGNITO_IAM_AUTH_PROVIDER_HEADER_NAME: f"{iam_auth_provider}"
    }


def api_request_id_header(request_id: str) -> Dict:
    """Constructs a dictionary representing the 'X-Api-RequestId' header.

    This utility function helps in programmatically creating HTTP headers that
    include a specific request ID.

    Args:
        request_id (str): The unique ID for the API request.

    Returns:
        Dict: A dictionary with the header name as key and the request ID as value.
    """
    return {
        AWS_API_REQUEST_ID_HEADER_NAME: f"{request_id}"
    }


class RequestContext(BaseModel):
    """Represents the context of an incoming API request, primarily focusing on identity
    and request tracking.

    This Pydantic model is designed to easily parse relevant HTTP headers
    ('X-Cognito-AuthProvider' for identity and 'X-Api-RequestId' for tracking)
    into structured attributes. It also provides utility methods for serialization
    and creating contexts programmatically.

    Attributes:
        identity_id (uuid.UUID): The UUID representing the user's identity
            obtained from the 'X-Cognito-AuthProvider' header. This field is frozen.
        request_id (Optional[str]): The unique ID for the API request, obtained
            from the 'X-Api-RequestId' header or newly generated if not present.
            This field is frozen.
    """
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
        """Returns the request context attributes as a dictionary suitable for HTTP headers.

        The keys in the returned dictionary will use their aliased names
        (e.g., 'X-Cognito-AuthProvider', 'X-Api-RequestId').

        Returns:
            dict: A dictionary of the request context headers.
        """
        return self.model_dump(by_alias=True)

    @classmethod
    def from_identity_id(cls, identity_id: uuid.UUID) -> Self:
        """Creates a RequestContext instance using a given identity UUID and generates a new request ID.

        This factory method is useful when you need to construct a `RequestContext`
        for internal use or testing, providing only the user's identity.

        Args:
            identity_id (uuid.UUID): The UUID of the user's identity.

        Returns:
            Self: A new `RequestContext` instance.
        """
        return cls(
            identity_id=identity_id, request_id=random_request_id()
        )

    @field_serializer('identity_id')
    @classmethod
    def serialize_identity_id(cls, identity_id: uuid.UUID, _):
        """Serializes the `identity_id` UUID into its string representation for output.

        Args:
            identity_id (uuid.UUID): The UUID object of the identity.
            _ (Any): Pydantic's SerializationInfo object (unused here).

        Returns:
            str: The string representation of the UUID.
        """
        return str(identity_id)

    @field_validator('identity_id', mode='before')
    @classmethod
    def validate_identity_id(cls, identity_id: str | uuid.UUID):
        """Validates and converts the `identity_id` from a string header to a UUID object.

        This validator runs before Pydantic model instantiation. It expects
        either a direct UUID object or the full 'X-Cognito-AuthProvider'
        header string, from which it extracts the UUID.

        Args:
            identity_id (str | uuid.UUID): The raw value for the identity,
                which can be the full header string or a UUID object.

        Returns:
            uuid.UUID: The validated UUID object for the identity.

        Raises:
            RequestValidationError: If the `identity_id` is None, indicating a
                missing required header.
        """
        if identity_id is None:
            raise RequestValidationError(
                errors=['missing identity identifier']
            )

        return (
            identity_id if isinstance(identity_id, uuid.UUID)
            else get_user_pool_identity_from_iam_auth_provider(identity_id)
        )
