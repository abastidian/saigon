import json
import pathlib
import uuid
import time
from typing import Optional, Self, Type, TypeVar, Callable, override, Dict, Tuple

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

RequestContentTypeDef = TypeVar('RequestContentTypeDef', bound=BaseModel)
ResponseContentTypeDef = TypeVar('ResponseContentTypeDef', bound=BaseModel)


class SigV4Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')

    access_key: str
    secret_key: str
    token: str

    @classmethod
    def from_credentials(cls, credentials: CredentialsTypeDef) -> Self:
        return cls(
            access_key=credentials['AccessKeyId'],
            secret_key=credentials['SecretKey'],
            token=credentials['SessionToken']
        )


class RestClientBase:
    def __init__(
            self, api_base_url: str, **kwargs
    ):
        self._api_base_url = api_base_url

    @classmethod
    def wait_for_condition(
            cls, condition: Callable[..., bool], timeout_sec: int = 60
    ):
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
        with open(filepath, "rb") as object_file:
            file_content = object_file.read()
            response = requests.put(
                s3_presigned_url,
                data=file_content,
                headers={}
            )
            response.raise_for_status()

    def _sign_request(self, aws_request: AWSRequest) -> AWSRequest:
        # No signing in base class
        return aws_request

    def get_resource(
            self,
            response_type: Type[ResponseContentTypeDef],
            endpoint: str,
            query_params: Optional[QueryDataParams] = None,
            headers: Optional[dict] = None
    ) -> ResponseContentTypeDef:
        return self.__send_request(
            'GET',
            endpoint,
            extra_headers=headers,
            response_type=response_type,
            params=query_params.url_params_dict if query_params else None
        )

    def create_resource(
            self,
            response_type: Type[ResponseContentTypeDef],
            endpoint: str,
            content: Optional[RequestContentTypeDef] = None,
            headers: Optional[dict] = None
    ) -> ResponseContentTypeDef:
        return self.__send_request(
            'POST',
            endpoint,
            extra_headers=headers,
            content=content,
            response_type=response_type
        )

    def delete_resource(
            self, endpoint: str, headers: Optional[dict] = None
    ):
        return self.__send_request(
            'DELETE',
            endpoint,
            extra_headers=headers,
        )

    def __build_request(
            self,
            method: str,
            endpoint: str,
            params: Optional[dict] = None,
            extra_headers: Optional[dict] = None,
            content: Optional[dict] = None
    ) -> AWSRequest:
        target_url = self._api_base_url + endpoint
        headers = extra_headers.copy() if extra_headers else {}
        headers.update(
            {
                "Host": target_url.split("//")[1].split("/")[0],  # Extract host from URL
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
            response_type: Optional[Type[ResponseContentTypeDef]] = None
    ) -> ResponseContentTypeDef | EmptyResponseBody:
        method_impls: Dict[str, Callable] = {
            'GET': requests.get,
            'POST': requests.post,
            'PUT': requests.put,
            'DELETE': requests.delete
        }
        payload = to_jsonable_python(content) if content else None
        aws_request = self.__build_request(
            method, endpoint, params, extra_headers, payload
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
    def __init__(self, alb_dns: str, service_port: int, api_version: str):
        super().__init__(
            f"http://{alb_dns}:{service_port}/{api_version}"
        )


class AuthRestClient(RestClientBase):
    def __init__(
            self,
            api_base_url: str,
            cognito_config: CognitoClientConfig
    ):
        super().__init__(api_base_url)
        self._cognito_client = CognitoClient(cognito_config)
        self._logins: Dict[str, Dict] = {}
        self._current_user: Optional[str] = None

    @property
    def current_user(self) -> Optional[Tuple[str, uuid.UUID]]:
        return (
            self._current_user, self._logins[self._current_user]['user_id']
        ) if self._current_user else None

    def login(self, username: str, password: str) -> Tuple[uuid.UUID, CredentialsTypeDef]:
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
        if (credentials := self._logins.get(username, None)) is None:
            raise KeyError(f"Invalid username={username}")

        self._current_user = username
        return credentials['user_id']

    @property
    def credentials(self) -> SigV4Credentials:
        return SigV4Credentials.from_credentials(
            self._logins[self._current_user]
        )

    @override
    def _sign_request(self, aws_request: AWSRequest) -> AWSRequest:
        if not self._current_user:
            raise ValueError('User is not logged in')

        SigV4Auth(
            self.credentials,
            "execute-api",
            self._cognito_client.aws_region
        ).add_auth(aws_request)

        return aws_request
