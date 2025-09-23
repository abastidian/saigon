import uuid
import json
from typing import Dict, Optional, Tuple, override

from requests import Request
import jwt

from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth
from mypy_boto3_cognito_identity.type_defs import CredentialsTypeDef

from pydantic import Field, BaseModel

from ..interface import RequestAuthorizer
from ..rest import RestClient
from .cognito import (
    CognitoClientConfig, CognitoClient
)

__all__ = [
    'SIGv4RequestAuthorizer',
    'AwsSIGv4RestClient'
]


class SigV4Credentials(BaseModel):
    access_key: str = Field(validation_alias='AccessKeyId')
    secret_key: str = Field(validation_alias='SecretKey')
    token: str = Field(validation_alias='SessionToken')
    user_id: uuid.UUID


class SIGv4RequestAuthorizer(RequestAuthorizer):
    def __init__(self, cognito_client: CognitoClient):
        self._client = cognito_client
        self._current_user: Optional[str] = None
        self._logins: Dict[str, SigV4Credentials] = {}

    @property
    def current_user(self) -> Optional[Tuple[str, uuid.UUID]]:
        """Returns the currently logged-in username and their UUID identity.

        Returns:
            Optional[Tuple[str, uuid.UUID]]: A tuple containing the username and
                their UUID if a user is logged in, otherwise None.
        """
        return (
            self._current_user, self._logins[self._current_user]['user_id']
        ) if self._current_user else None

    def login(
            self, username: str, password: str
    ) -> SigV4Credentials:
        """Logs in a user via Cognito and retrieves IAM credentials.

        This method performs the user authentication against Cognito, extracts
        the user's UUID from the ID token, obtains temporary AWS IAM credentials,
        and stores them internally for subsequent authenticated requests.

        Args:
            username (str): The username for login.
            password (str): The password for login.

        Returns:
            Tuple[uuid.UUID, CredentialsTypeDef]: A tuple containing the user's UUID
                and the AWS IAM credentials obtained from Cognito.
        """
        login_result = self._client.login_user(
            username, password
        )
        user_id = uuid.UUID(
            jwt.decode(
                login_result['IdToken'],
                options={"verify_signature": False},
                algorithms=["RS256"]
            ).get('sub')
        )
        login_credentials = self._client.get_iam_credentials(
            login_result['IdToken']
        )
        self._current_user = username
        self._logins[username] = SigV4Credentials(
            **login_credentials, user_id=user_id
        )
        return self._logins[username]

    def switch_user(self, username: str) -> uuid.UUID:
        """Switches the active user for subsequent requests.

        The user must have previously logged in using the `login` method.
        This updates the internal state to use the credentials of the specified user.

        Args:
            username (str): The username to switch to.

        Returns:
            uuid.UUID: The UUID of the newly active user.

        Raises:
            KeyError: If the provided `username` has not logged in previously.
        """
        if (credentials := self._logins.get(username, None)) is None:
            raise KeyError(f"Invalid username={username}")

        self._current_user = username
        return credentials['user_id']

    @override
    def authorize(self, request: Request) -> Request:
        """Implementation that signs an AWSRequest using SigV4 authentication with
        the current user's credentials, which must be present or else this operation
        will fail.

        Args:
            request (Request): The Request object to be signed.

        Returns:
            Request: The signed Request object.

        Raises:
            ValueError: If no user is currently logged in.
                """
        if not self._current_user:
            raise ValueError('User is not logged in')

        aws_signed_request = AWSRequest(
            method=request.method,
            url=request.url,
            headers=request.headers,
            data=json.dumps(request.data) if request.data else "",
            params=request.params
        )
        SigV4Auth(
            self._logins.get(self._current_user),
            "execute-api",
            self._client.aws_region
        ).add_auth(aws_signed_request)

        return Request(
            method=aws_signed_request.method,
            url=aws_signed_request.url,
            headers=aws_signed_request.headers,
            data=request.data,
            params=aws_signed_request.params
        )


class AwsSIGv4RestClient(RestClient):
    """A REST client that integrates with AWS Cognito for authentication and SigV4 signing.

    This client extends `RestClientBase` to provide user login capabilities
    via Cognito and automatically sign all outgoing requests with AWS SigV4,
    using temporary IAM credentials obtained from Cognito.
    """

    def __init__(
            self,
            api_base_url: str,
            cognito_config: CognitoClientConfig
    ):
        """Initializes the AuthRestClient.

        Args:
            api_base_url (str): The base URL of the API service.
            cognito_config (CognitoClientConfig): Configuration for the Cognito client.
        """
        super().__init__(
            api_base_url,
            authorizer=SIGv4RequestAuthorizer(
                CognitoClient(cognito_config)
            )
        )

    @property
    def authorizer(self) -> SIGv4RequestAuthorizer:
        return self._authorizer
