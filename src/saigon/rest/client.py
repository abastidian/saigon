import time
from pathlib import Path
from functools import cached_property
from typing import Optional, Type, Callable, Dict, Union, override

import requests

from pydantic import BaseModel
from pydantic_core import to_jsonable_python
from requests import Request

from ..model import EmptyContent
from ..interface import RequestAuthorizer


__all__ = [
    'RestClient',
    'BackendRestClient',
    'upload_file_to_url'
]


class NoAuthRequestAuthorizer(RequestAuthorizer):
    @override
    def authorize(self, request: Request) -> Request:
        return request


class RestClient:
    """Base class for REST API clients.

    Provides common functionalities for making HTTP requests,
    waiting for conditions, and handling S3 pre-signed URL uploads.
    It can be extended for specific backend services and authentication mechanisms.
    """

    def __init__(
            self,
            service_url: str,
            service_port: int | None = None,
            api_prefix: Optional[str] = '',
            authorizer=NoAuthRequestAuthorizer()
    ):
        """Initializes the RestClientBase.

        Args:
            service_url (str): The base URL of the service (e.g., "http://localhost").
            service_port (Optional[int]): The port number of the service. Defaults to None.
            api_prefix (Optional[str]): A prefix to add to all API endpoints (e.g., "/v1").
                Defaults to an empty string.
        """
        self._service_url = service_url
        self._service_port = service_port
        self._api_prefix = api_prefix
        self._authorizer = authorizer

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
            self._service_url
            + (f":{target_port}" if target_port else '')
            + self._api_prefix
        )

    @cached_property
    def _default_base_url(self):
        """Provides the default base URL for the service.

        This property is cached for efficiency.

        Returns:
            str: The default base URL.
        """
        return self._build_service_url()

    def get_resource[ResponseContentTypeDef: BaseModel](
            self,
            response_type: Type[ResponseContentTypeDef],
            endpoint: str,
            query_params: Optional[dict] = None,
            headers: Optional[dict] = None,
            service_port: Optional[int] = None
    ) -> ResponseContentTypeDef:
        """Sends a GET request to retrieve a resource.

        Args:
            response_type (Type[ResponseContentTypeDef]): The Pydantic model type
                to which the JSON response content should be deserialized.
            endpoint (str): The API endpoint path (e.g., "/items/123").
            query_params (Optional[dict]): An object containing query
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
            params=query_params,
            service_port=service_port
        )

    def create_resource[
        RequestContentTypeDef: BaseModel,
        ResponseContentTypeDef: BaseModel
    ](
        self,
        response_type: Type[ResponseContentTypeDef],
        endpoint: str,
        query_params: Optional[dict] = None,
        content: Optional[RequestContentTypeDef] = None,
        headers: Optional[dict] = None,
        service_port: Optional[int] = None
    ) -> ResponseContentTypeDef:
        """Sends a POST request to create a resource.

        Args:
            response_type (Type[ResponseContentTypeDef]): The Pydantic model type
                to which the JSON response content should be deserialized.
            endpoint (str): The API endpoint path (e.g., "/items").
            query_params (Optional[Dict]): Mapping of URL query parameters
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
            params=query_params,
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
    ) -> requests.Request:
        """Builds an `Request` object for a given HTTP request.

        This private method handles constructing the URL, setting default headers
        like 'Host', 'Accept', and 'Content-Type', and preparing the request body.
        It then calls `_sign_request` to apply any necessary authentication.

        Args:
            method (str): The HTTP method (e.g., 'GET', 'POST').
            endpoint (str): The API endpoint path.
            params (Optional[dict]): A dictionary of URL query parameters. Defaults to None.
            extra_headers (Optional[dict]): A dictionary of additional HTTP headers.
                Defaults to None.
            content (Optional[dict]): The request body content as a dictionary.
                It will be JSON-encoded. Defaults to None.
            service_port (Optional[int]): A specific port to use for this request.
                Defaults to None.

        Returns:
            Request: The constructed and potentially signed Request object.
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

        return self._authorizer.authorize(
            requests.Request(
                method=method,
                url=target_url,
                headers=headers,
                data=content,
                params=params
            )
        )

    def __send_request[
        RequestContentTypeDef: BaseModel,
        ResponseContentTypeDef: BaseModel
    ](
            self,
            method: str,
            endpoint: str,
            params: Optional[dict] = None,
            extra_headers: Optional[dict] = None,
            content: Optional[RequestContentTypeDef] = None,
            response_type: Optional[Type[ResponseContentTypeDef]] = None,
            service_port: Optional[int] = None
    ) -> Union[ResponseContentTypeDef, EmptyContent]:
        """Sends the actual HTTP request and processes the response.

        This private method selects the appropriate `requests` method based on
        the HTTP verb, builds the request, sends it, checks for HTTP errors,
        and deserializes the response content into the specified Pydantic model.

        Args:
            method (str): The HTTP method (e.g., 'GET', 'POST').
            endpoint (str): The API endpoint path.
            params (Optional[dict]): A dictionary of URL query parameters. Defaults to None.
            extra_headers (Optional[dict]): A dictionary of additional HTTP headers.
                Defaults to None.
            content (Optional[RequestContentTypeDef]): The request body content.
                Defaults to None.
            response_type (Optional[Type[ResponseContentTypeDef]]): The Pydantic model type
                for the response. If None, `EmptyContent` is returned.
                Defaults to None.
            service_port (Optional[int]): A specific port to use for this request.
                Defaults to None.

        Returns:
            Union[ResponseContentTypeDef, EmptyContent]: An instance of the
                `response_type` Pydantic model, or `EmptyContent` if no
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
        authorized_request = self.__build_request(
            method, endpoint, params, extra_headers, payload, service_port
        )
        response = method_impls[authorized_request.method](
            authorized_request.url,
            **dict(
                headers=dict(authorized_request.headers),
                params=authorized_request.params,
                json=authorized_request.data if authorized_request.data else None
            )
        )
        response.raise_for_status()
        return (
            response_type.model_validate_json(response.content)
            if response_type else EmptyContent()
        )


class BackendRestClient(RestClient):
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


def upload_file_to_url(
        filepath: Path,
        target_url: str,
        headers: Dict | None = None
):
    """Uploads a file to an provided URL using a PUT.

    Args:
        filepath (pathlib.Path): The path to the file to be uploaded.
        target_url (str): The target url where to PUT the request
        headers (Dict | None): Optional headers

    Raises:
        requests.exceptions.RequestException: If the HTTP PUT request to the
            pre-signed URL fails (non-2xx status code).
    """
    with open(filepath, "rb") as object_file:
        file_content = object_file.read()
        response = requests.put(
            target_url,
            data=file_content,
            headers=headers
        )
        response.raise_for_status()
