import uuid
import base64
from typing import Type, Optional, Self, Any, Callable

from pydantic import (
    BaseModel,
    Field,
    field_serializer,
    field_validator,
    ConfigDict,
    create_model
)


__all__ = [
    'HeaderContext',
    'DEFAULT_API_REQUEST_ID_HEADER_NAME',
    'DEFAULT_IDENTITY_ID_HEADER_NAME',
    'custom_request_context'
]

DEFAULT_IDENTITY_ID_HEADER_NAME = 'X-Api-IdentityId'
DEFAULT_API_REQUEST_ID_HEADER_NAME = 'X-Api-RequestId'


def random_request_id() -> str:
    """Generates a random URL-safe base64 encoded UUID for use as a request ID.

    Returns:
        str: A unique, URL-safe string representing a request ID.
    """
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode()


class HeaderContext[IdentityId: uuid.UUID | str](BaseModel):
    model_config = ConfigDict(
        validate_by_alias=True,
        validate_by_name=True
    )

    """Represents the context of an incoming API request, primarily focusing on identity
    and request tracking.

    This Pydantic model is designed to easily parse relevant HTTP headers
    It also provides utility methods for serialization and creating contexts programmatically.

    Attributes:
        identity_id (IdentityId): The unique identifier representing the user's identity
            obtained from the corresponding alias header. This field is frozen.
        request_id (Optional[str]): The unique ID for the API request, obtained
            from th corresponding alias header or newly generated if not present.
            This field is frozen.
    """
    identity_id: IdentityId = Field(
        alias=DEFAULT_IDENTITY_ID_HEADER_NAME,
        frozen=True
    )
    request_id: Optional[str] = Field(
        random_request_id(),
        alias=DEFAULT_API_REQUEST_ID_HEADER_NAME,
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
    def from_identity_id(cls, identity_id: IdentityId) -> Self:
        """Creates a RequestContext instance using a given identity UUID and generates
        a new request ID.

        This factory method is useful when you need to construct a `RequestContext`
        for internal use or testing, providing only the user's identity.

        Args:
            identity_id (uuid.UUID): The UUID of the user's identity.

        Returns:
            Self: A new `RequestContext` instance.
        """
        return cls(identity_id=identity_id)

    @field_serializer('identity_id')
    @classmethod
    def serialize_identity_id(cls, identity_id: uuid.UUID, _) -> str:
        """Serializes the `identity_id` UUID into its string representation for output.

        Args:
            identity_id (uuid.UUID): The UUID object of the identity.
            _ (Any): Pydantic's SerializationInfo object (unused here).

        Returns:
            str: The string representation of the UUID.
        """
        return str(identity_id)


def custom_request_context[IdentityId](
        type_name: str,
        identity_id_alias: Optional[str] = DEFAULT_IDENTITY_ID_HEADER_NAME,
        request_id_alias: Optional[str] = DEFAULT_API_REQUEST_ID_HEADER_NAME,
        identity_id_validator: Optional[Callable[[Any], IdentityId]] = None,
        request_id_validator: Optional[Callable[[Any], IdentityId]] = None
) -> Type[HeaderContext[IdentityId]]:
    """Creates a RequestContext model by overriding the attribute aliases and validators.

    You can select any combination of elements to override. The non-overridden will remain
    as defined in the default model.

    Args:
        identity_id_alias (Optional[str]): Overriding alias for identity_id
        request_id_alias (Optional[str]): Overriding alias for request_id
        identity_id_validator (Optional[Callable]): Overriding validator for identity_id
        request_id_validator: (Optional[Callable]): Overriding validator for request_id

    Returns:
        HeaderContext[IdentityId]: A model subclass of RequestContext with the overriding
        values

    """
    validators = {}
    if identity_id_validator:
        validators['identity_id_validator'] = field_validator('identity_id')(
            identity_id_validator
        )
    if request_id_validator:
        validators['request_id_validator'] = field_validator('request_id')(request_id_validator)

    return create_model(
        type_name,
        __base__=HeaderContext[IdentityId],
        identity_id=(IdentityId, Field(alias=identity_id_alias)),
        request_id=(Optional[str], Field(random_request_id(), alias=request_id_alias)),
        __validators__=validators
    )
