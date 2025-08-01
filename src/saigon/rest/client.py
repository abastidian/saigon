import json
import pathlib
import uuid
import time
from functools import cached_property
from typing import Optional, Self, Type, TypeVar, Callable, override, Dict, Tuple, Union

import requests
import jwt

from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth
from mypy_boto3_cognito_identity.type_defs import CredentialsTypeDef

from pydantic import BaseModel, ConfigDict
from pydantic_core import to_jsonable_python

from ..aws.cognito import CognitoClient, CognitoClientConfig
from ..fastapi.handlers import EmptyResponseBody
from ..model import QueryDataParams

# Type variable for the request content (must be a Pydantic BaseModel).
RequestContentTypeDef = TypeVar('RequestContentTypeDef', bound=BaseModel)
# Type variable for the response content (must be a Pydantic BaseModel).
ResponseContentTypeDef = TypeVar('ResponseContentTypeDef', bound=BaseModel)


class SigV4Credentials(BaseModel):
    """Represents AWS Signature Version 4 credentials.

    This model is used to encapsulate the necessary components for
    authenticating requests using AWS SigV4.

    Attributes:
        access_key (str): The AWS access key ID.
        secret_key (str): The AWS secret access key.
        token (str): The AWS session token (for temporary credentials).
    """
    model_config = ConfigDict(extra='forbid')

    access_key: str
    secret_key: str
    token: str

    @classmethod
    def from_credentials(cls, credentials: CredentialsTypeDef) -> Self:
        """Creates a SigV4Credentials instance from a `CredentialsTypeDef` dictionary.

        Args:
            credentials (CredentialsTypeDef): A dictionary containing AWS credentials,
                typically obtained from boto3 (e.g., Cognito Identity `get_credentials_for_identity`).

        Returns:
            Self: A new `SigV4Credentials` instance.
        """
        return cls(
            access_key=credentials['AccessKeyId'],
            secret_key=credentials['SecretKey'],
            token=credentials['SessionToken']
        )


class RestClientBase:
    """Base class for REST API clients.

    Provides common functionalities for making HTTP requests,
    waiting for conditions, and handling S3 pre-signed URL uploads.
    It can be extended for specific backend services and authentication mechanisms.
    """
    def __init__(
            self,
            service_url: str,
            service_port: Optional[int] = None,
            api_prefix: Optional[str] = '',
            **kwargs
    ):
        """Initializes the RestClientBase.

        Args:
            service_url (str): The base URL of the service (e.g., "http://localhost").
            service_port (Optional[int]): The port number of the service. Defaults to None.
            api_prefix (Optional[str]): A prefix to add to all API endpoints (e.g., "/v1").
                Defaults to an empty string.
            **kwargs: Additional keyword arguments.
        """
        self._service_url = service_url
        self._service_port = service_port
        self._api_prefix = api_prefix

    @classmethod
    def wait_for_condition(
            cls, condition: Callable[..., bool], timeout_sec: int = 60
    ):
        """Waits for a given condition to become true within a specified timeout.

        This method polls the `condition` callable at regular intervals (2 seconds)
        until it returns True or the `timeout_sec` is reached.

        Args:
            condition (Callable[..., bool]): A callable that returns True when the
                desired condition is met, and False otherwise.
            timeout_sec (int): The maximum number of seconds to wait for the
                condition. Defaults to 60.

        Raises:
            TimeoutError: If the condition is not met within the specified timeout.
        """
        polling_period_sec = 2
        for i in range(0, int(timeout_sec / 2) + 1):
            if condition():
                return

            time.sleep(polling_period_sec)

        raise TimeoutError('condition not met in time')

    @classmethod
    def upload_file_to_s3_presigned_url(
            cls,
            filepath: pathlib.Path,
            s3_presigned_url: str
    ):
        """Uploads a file to an S3 bucket using a pre-signed URL.

        Args:
            filepath (pathlib.Path): The path to the file to be uploaded.
            s3_presigned_url (str): The pre-signed URL generated by S3 for the upload.

        Raises:
            requests.exceptions.RequestException: If the HTTP PUT request to the
                pre-signed URL fails (non-2xx status code).
        """
        with open(filepath, "rb") as object_file:
            file_content = object_file.read()
            response = requests.put(
                s3_presigned_url,
                data=file_content,
                headers={}
            )
            response.raise_for_status()

    def _build_service_url(self, service_port: Optional[int] = None):
        """Constructs the full service URL based on base URL, optional port, and API prefix.

        Args:
            service_port (Optional[int]): A specific port to use for this build,
                overriding the instance's default port if provided.

        Returns:
            str: The fully constructed service URL.
        """
        target_port = service_port if service_port else self._service_port
        return (
            self._service_url + f":{target_port}" if target_port else '' + self._api_prefix
        )

    @cached_property
    def _default_base_url(self):
        """Provides the default base URL for the service.

        This property is cached for efficiency.

        Returns:
            str: The default base URL.
        """
        return self._build_service_url()

    def _sign_request(self, aws_request: AWSRequest) -> AWSRequest:
        """Abstract method for signing an AWS request.

        This method is intended to be overridden by subclasses that implement
        specific signing mechanisms (e.g., SigV4). In the base class, it performs
        no signing.

        Args:
            aws_request (AWSRequest): The AWSRequest object to be signed.

        Returns:
            AWSRequest: The potentially signed AWSRequest object.
        """
        # No signing in base class
        return aws_request

    def get_resource(
            self,
            response_type: Type[ResponseContentTypeDef],
            endpoint: str,
            query_params: Optional[QueryDataParams] = None,
            headers: Optional[dict] = None,
            service_port: Optional[int] = None
    ) -> ResponseContentTypeDef:
        """Sends a GET request to retrieve a resource.

        Args:
            response_type (Type[ResponseContentTypeDef]): The Pydantic model type
                to which the JSON response content should be deserialized.
            endpoint (str): The API endpoint path (e.g., "/items/123").
            query_params (Optional[QueryDataParams]): An object containing query
                parameters. Its `url_params_dict` will be used. Defaults to None.
            headers (Optional[dict]): A dictionary of additional HTTP headers to send.
                Defaults to None.
            service_port (Optional[int]): A specific port to use for this request,
                overriding the instance's default port. Defaults to None.

        Returns:
            ResponseContentTypeDef: An instance of the `response_type` Pydantic model
                populated with the response data.
        """
        return self.__send_request(
            'GET',
            endpoint,
            extra_headers=headers,
            response_type=response_type,
            params=query_params.url_params_dict if query_params else None,
            service_port=service_port
        )

    def create_resource(
            self,
            response_type: Type[ResponseContentTypeDef],
            endpoint: str,
            content: Optional[RequestContentTypeDef] = None,
            headers: Optional[dict] = None,
            service_port: Optional[int] = None
    ) -> ResponseContentTypeDef:
        """Sends a POST request to create a resource.

        Args:
            response_type (Type[ResponseContentTypeDef]): The Pydantic model type
                to which the JSON response content should be deserialized.
            endpoint (str): The API endpoint path (e.g., "/items").
            content (Optional[RequestContentTypeDef]): An instance of a Pydantic model
                representing the request body. It will be serialized to JSON. Defaults to None.
            headers (Optional[dict]): A dictionary of additional HTTP headers to send.
                Defaults to None.
            service_port (Optional[int]): A specific port to use for this request,
                overriding the instance's default port. Defaults to None.

        Returns:
            ResponseContentTypeDef: An instance of the `response_type` Pydantic model
                populated with the response data.
        """
        return self.__send_request(
            'POST',
            endpoint,
            extra_headers=headers,
            content=content,
            response_type=response_type,
            service_port=service_port
        )

    def delete_resource(
            self,
            endpoint: str,
            headers: Optional[dict] = None,
            service_port: Optional[int] = None
    ):
        """Sends a DELETE request to remove a resource.

        Args:
            endpoint (str): The API endpoint path (e.g., "/items/123").
            headers (Optional[dict]): A dictionary of additional HTTP headers to send.
                Defaults to None.
            service_port (Optional[int]): A specific port to use for this request,
                overriding the instance's default port. Defaults to None.
        """
        return self.__send_request(
            'DELETE',
            endpoint,
            extra_headers=headers,
            service_port=service_port
        )

    def __build_request(
            self,
            method: str,
            endpoint: str,
            params: Optional[dict] = None,
            extra_headers: Optional[dict] = None,
            content: Optional[dict] = None,
            service_port: Optional[int] = None
    ) -> AWSRequest:
        """Builds an `AWSRequest` object for a given HTTP request.

        This private method handles constructing the URL, setting default headers
        like 'Host', 'Accept', and 'Content-Type', and preparing the request body.
        It then calls `_sign_request` to apply any necessary authentication.

        Args:
            method (str): The HTTP method (e.g., 'GET', 'POST').
            endpoint (str): The API endpoint path.
            params (Optional[dict]): A dictionary of URL query parameters. Defaults to None.
            extra_headers (Optional[dict]): A dictionary of additional HTTP headers. Defaults to None.
            content (Optional[dict]): The request body content as a dictionary. It will be JSON-encoded.
                Defaults to None.
            service_port (Optional[int]): A specific port to use for this request. Defaults to None.

        Returns:
            AWSRequest: The constructed and potentially signed AWSRequest object.
        """
        service_base_url = (
            self._build_service_url(service_port) if service_port
            else self._default_base_url
        )
        target_url = service_base_url + endpoint
        headers = extra_headers.copy() if extra_headers else {}
        headers.update(
            {
                "Host": target_url.split("//")[-1].split("/")[0],  # Extract host from URL
            }
        )
        match (method.upper()):
            case 'GET':
                headers['Accept'] = 'application/json'
            case _:
                headers['Content-Type'] = 'application/json'

        return self._sign_request(
            AWSRequest(
                method=method,
                url=target_url,
                headers=headers,
                data=json.dumps(content) if content else "",
                params=params
            )
        )

    def __send_request(
            self,
            method: str,
            endpoint: str,
            params: Optional[dict] = None,
            extra_headers: Optional[dict] = None,
            content: Optional[RequestContentTypeDef] = None,
            response_type: Optional[Type[ResponseContentTypeDef]] = None,
            service_port: Optional[int] = None
    ) -> Union[ResponseContentTypeDef, EmptyResponseBody]:
        """Sends the actual HTTP request and processes the response.

        This private method selects the appropriate `requests` method based on
        the HTTP verb, builds the request, sends it, checks for HTTP errors,
        and deserializes the response content into the specified Pydantic model.

        Args:
            method (str): The HTTP method (e.g., 'GET', 'POST').
            endpoint (str): The API endpoint path.
            params (Optional[dict]): A dictionary of URL query parameters. Defaults to None.
            extra_headers (Optional[dict]): A dictionary of additional HTTP headers. Defaults to None.
            content (Optional[RequestContentTypeDef]): The request body content. Defaults to None.
            response_type (Optional[Type[ResponseContentTypeDef]]): The Pydantic model type
                for the response. If None, `EmptyResponseBody` is returned. Defaults to None.
            service_port (Optional[int]): A specific port to use for this request. Defaults to None.

        Returns:
            Union[ResponseContentTypeDef, EmptyResponseBody]: An instance of the
                `response_type` Pydantic model, or `EmptyResponseBody` if no
                `response_type` was provided.

        Raises:
            requests.exceptions.RequestException: If the HTTP request fails
                (non-2xx status code).
        """
        method_impls: Dict[str, Callable] = {
            'GET': requests.get,
            'POST': requests.post,
            'PUT': requests.put,
            'DELETE': requests.delete
        }
        payload = to_jsonable_python(content) if content else None
        aws_request = self.__build_request(
            method, endpoint, params, extra_headers, payload, service_port
        )
        response = method_impls[aws_request.method](
            aws_request.url,
            **dict(
                headers=dict(aws_request.headers),
                params=aws_request.params,
                json=payload
            )
        )
        response.raise_for_status()
        return (
            response_type.model_validate_json(response.content)
            if response_type else EmptyResponseBody()
        )


class BackendRestClient(RestClientBase):
    """A specific REST client for a backend service, built on `RestClientBase`.

    This client is configured with a specific ALB DNS, service port, and API version,
    tailored for a typical backend service deployment.
    """
    def __init__(
        self, alb_dns: str, service_port: int, api_version: str
    ):
        """Initializes the BackendRestClient.

        Args:
            alb_dns (str): The DNS name of the Application Load Balancer (ALB)
                fronting the backend service.
            service_port (int): The port number on which the backend service is listening.
            api_version (str): The API version prefix for the endpoints (e.g., "v1").
        """
        super().__init__(
            f"http://{alb_dns}", service_port, f"/{api_version}"
        )


class AuthRestClient(RestClientBase):
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
        super().__init__(api_base_url)
        self._cognito_client = CognitoClient(cognito_config)
        self._logins: Dict[str, Dict] = {}
        self._current_user: Optional[str] = None

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

    def login(self, username: str, password: str) -> Tuple[uuid.UUID, CredentialsTypeDef]:
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
        login_result = self._cognito_client.login_user(
            username, password
        )
        user_id = uuid.UUID(
            jwt.decode(
                login_result['IdToken'], options={"verify_signature": False}, algorithms=["RS256"]
            ).get('sub')
        )
        login_credentials = self._cognito_client.get_iam_credentials(
            login_result['IdToken']
        )
        self._current_user = username
        self._logins[username] = {**login_credentials, 'user_id': user_id}
        return user_id, login_credentials

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

    @property
    def credentials(self) -> SigV4Credentials:
        """Returns the SigV4 credentials for the currently logged-in user.

        These credentials are used to sign outgoing requests.

        Returns:
            SigV4Credentials: The SigV4 credentials for the current user.

        Raises:
            KeyError: If no user is currently logged in or the current user's
                credentials are not available.
        """
        return SigV4Credentials.from_credentials(
            self._logins[self._current_user]
        )

    @override
    def _sign_request(self, aws_request: AWSRequest) -> AWSRequest:
        """Signs an AWSRequest using SigV4 authentication with the current user's credentials.

        This method overrides the base class's `_sign_request` to apply AWS
        Signature Version 4 authentication to the outgoing request. It requires
        a user to be logged in.

        Args:
            aws_request (AWSRequest): The AWSRequest object to be signed.

        Returns:
            AWSRequest: The signed AWSRequest object.

        Raises:
            ValueError: If no user is currently logged in (`_current_user` is None).
        """
        if not self._current_user:
            raise ValueError('User is not logged in')

        SigV4Auth(
            self.credentials,
            "execute-api",
            self._cognito_client.aws_region
        ).add_auth(aws_request)

        return aws_request
