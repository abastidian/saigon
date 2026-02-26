import time
from pathlib import Path
from functools import cached_property
from typing import Optional, Type, Callable, Dict, Union, override

import requests
import httpx

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from ..model import EmptyContent, BasicRestResponse
from ..interface import RequestAuthorizer, AsyncRequestAuthorizer

RequestBodyContent = Union[BaseModel, str, bytes]

__all__ = [
    'RequestBodyContent',
    'RestClient',
    'AsyncRestClient',
    'BackendRestClient',
    'upload_file_to_url'
]


class NoAuthRequestAuthorizer(RequestAuthorizer):
    @override
    def authorize(self, request: requests.Request) -> requests.Request:
        return request


class AsyncNoAuthRequestAuthorizer(AsyncRequestAuthorizer):
    @override
    async def authorize(self, request: requests.Request) -> requests.Request:
        return request


class _RestClientBase:
    """Base class for REST API clients implementations."""

    def __init__(
            self,
            service_url: str,
            service_port: int | None = None,
            api_prefix: Optional[str] = ''
    ):
        self._service_url = service_url
        self._service_port = service_port
        self._api_prefix = api_prefix

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

    @staticmethod
    def _resolve_content_type(headers: dict) -> str:
        """Case-insensitive lookup of Content-Type from a headers dict.

        Args:
            headers (dict): The headers dictionary to search.

        Returns:
            str: The Content-Type value if found, otherwise 'application/json'.
        """
        for key, value in headers.items():
            if key.lower() == 'content-type':
                return value
        return 'application/json'

    @staticmethod
    def _serialize_body(content_type: str, content: RequestBodyContent) -> object:
        """Serialize request body according to the resolved Content-Type.

        Args:
            content_type (str): The resolved Content-Type header value.
            content (RequestBodyContent): The request body content.

        Returns:
            The serialized body appropriate for the given content type.

        Raises:
            ValueError: If content_type is 'application/xml' and content is a BaseModel instance.
        """
        match content_type:
            case 'application/json' | 'application/x-www-form-urlencoded':
                return to_jsonable_python(content)
            case 'application/xml':
                if isinstance(content, BaseModel):
                    raise ValueError(
                        "BaseModel instances cannot be serialized as XML. "
                        "Pass pre-serialized str or bytes."
                    )
                return content
            case 'text/plain':
                if isinstance(content, BaseModel):
                    return content.model_dump_json()
                return content
            case _:
                return content

    @staticmethod
    def _build_body_kwargs(content_type: str, data: object) -> dict:
        """Map serialized body data to the appropriate httpx keyword argument.

        Args:
            content_type (str): The resolved Content-Type header value.
            data: The serialized request body from ``_serialize_body``.

        Returns:
            dict: A single-entry dict with the correct httpx kwarg key
                (``json``, ``data``, or ``content``), or empty if data is None.
        """
        if data is None:
            return {}
        if content_type == 'application/json':
            return {'json': data}
        if content_type == 'application/x-www-form-urlencoded':
            return {'data': data}
        return {'content': data}

    def _build_request(
            self,
            method: str,
            endpoint: str,
            params: Optional[dict] = None,
            extra_headers: Optional[dict] = None,
            content: Optional[RequestBodyContent] = None,
            service_port: Optional[int] = None
    ) -> requests.Request:
        """Builds an `Request` object for a given HTTP request.

        This private method handles constructing the URL, setting default headers
        like 'Host', 'Accept', and 'Content-Type', and preparing the request body.
        It then calls `_sign_request` to apply any necessary authentication.

        Default headers are only applied when not already present in `extra_headers`.
        The check is case-insensitive, so providing 'accept' or 'ACCEPT' in
        `extra_headers` will prevent the default 'Accept: application/json' from
        being set on GET requests. Similarly, 'content-type' or 'CONTENT-TYPE'
        will prevent the default 'Content-Type: application/json' on non-GET requests.

        Args:
            method (str): The HTTP method (e.g., 'GET', 'POST').
            endpoint (str): The API endpoint path.
            params (Optional[dict]): A dictionary of URL query parameters. Defaults to None.
            extra_headers (Optional[dict]): A dictionary of additional HTTP headers.
                Can override default 'Accept' (GET) and 'Content-Type' (non-GET) headers.
                Defaults to None.
            content (Optional[RequestBodyContent]): The request body content.
                Can be a Pydantic BaseModel, a raw str, or raw bytes. The serialization
                strategy is determined by the resolved Content-Type header. Defaults to None.
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
        existing_keys = {k.lower() for k in headers}
        match (method.upper()):
            case 'GET':
                if 'accept' not in existing_keys:
                    headers['Accept'] = 'application/json'
            case _:
                if 'content-type' not in existing_keys:
                    headers['Content-Type'] = 'application/json'

        serialized_body = None
        if content is not None:
            serialized_body = _RestClientBase._serialize_body(
                _RestClientBase._resolve_content_type(headers),
                content
            )

        return requests.Request(
            method=method,
            url=target_url,
            headers=headers,
            data=serialized_body,
            params=params
        )

    @classmethod
    def _process_response[
        ResponseContentTypeDef: BaseModel
    ](
            cls,
            response: httpx.Response,
            response_type: Optional[Type[ResponseContentTypeDef]] = None,
    ):
        response.raise_for_status()

        if response_type is None:
            return EmptyContent()

        if issubclass(response_type, BasicRestResponse):
            return BasicRestResponse(
                status_code=response.status_code,
                content=response.text
            )

        response_content_type = _RestClientBase._resolve_content_type(dict(response.headers))
        if response_content_type.startswith('application/json'):
            return response_type.model_validate_json(response.content)

        return BasicRestResponse(
            status_code=response.status_code,
            content=response.text
        )

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


class AsyncRestClient(_RestClientBase):
    """Async Rest Client.

    Provides common functionalities for making HTTP requests,
    waiting for conditions, and handling S3 pre-signed URL uploads.
    It can be extended for specific backend services and authentication mechanisms.
    """

    def __init__(
            self,
            service_url: str,
            service_port: int | None = None,
            api_prefix: Optional[str] = '',
            authorizer=AsyncNoAuthRequestAuthorizer()
    ):
        """Initializes the RestClientBase.

        Args:
            service_url (str): The base URL of the service (e.g., "http://localhost").
            service_port (Optional[int]): The port number of the service. Defaults to None.
            api_prefix (Optional[str]): A prefix to add to all API endpoints (e.g., "/v1").
                Defaults to an empty string.
        """
        super().__init__(service_url, service_port, api_prefix)
        self._authorizer = authorizer
        self._client = httpx.AsyncClient()

    async def close(self):
        if self._client is not None:
            await self._client.aclose()

    async def get_resource[ResponseContentTypeDef: BaseModel](
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
        return await self.__send_request(
            'GET',
            endpoint,
            extra_headers=headers,
            response_type=response_type,
            params=query_params,
            service_port=service_port
        )

    async def create_resource[
        ResponseContentTypeDef: BaseModel
    ](
        self,
        response_type: Type[ResponseContentTypeDef],
        endpoint: str,
        query_params: Optional[dict] = None,
        content: Optional[RequestBodyContent] = None,
        headers: Optional[dict] = None,
        service_port: Optional[int] = None
    ) -> ResponseContentTypeDef:
        """Sends a POST request to create a resource.

        Args:
            response_type (Type[ResponseContentTypeDef]): The Pydantic model type
                to which the JSON response content should be deserialized.
            endpoint (str): The API endpoint path (e.g., "/items").
            query_params (Optional[Dict]): Mapping of URL query parameters
            content (Optional[RequestBodyContent]): The request body.
                Accepts a Pydantic BaseModel instance (serialized according to Content-Type),
                a raw ``str``, or raw ``bytes``. Defaults to None.
                When ``headers`` includes a ``Content-Type`` override, the body is serialized
                accordingly; otherwise defaults to JSON serialization.
            headers (Optional[dict]): A dictionary of additional HTTP headers to send.
                May include ``Content-Type`` to control body serialization and ``Accept``
                to control the expected response format. Defaults to None.
            service_port (Optional[int]): A specific port to use for this request,
                overriding the instance's default port. Defaults to None.

        Returns:
            ResponseContentTypeDef: An instance of the `response_type` Pydantic model
                populated with the response data.
        """
        return await self.__send_request(
            'POST',
            endpoint,
            params=query_params,
            extra_headers=headers,
            content=content,
            response_type=response_type,
            service_port=service_port
        )

    async def delete_resource(
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
        await self.__send_request(
            'DELETE',
            endpoint,
            extra_headers=headers,
            service_port=service_port
        )

    async def __send_request[
        ResponseContentTypeDef: BaseModel
    ](
            self,
            method: str,
            endpoint: str,
            params: Optional[dict] = None,
            extra_headers: Optional[dict] = None,
            content: Optional[RequestBodyContent] = None,
            response_type: Optional[Type[ResponseContentTypeDef]] = None,
            service_port: Optional[int] = None
    ) -> Union[ResponseContentTypeDef, EmptyContent]:
        """Sends the actual HTTP request and processes the response.

        This private method selects the appropriate `requests` method based on
        the HTTP verb, builds the request, sends it, checks for HTTP errors,
        and deserializes the response content into the specified Pydantic model.

        The request body is dispatched to the correct httpx parameter based on
        the resolved Content-Type header:
        - ``application/json`` → ``json=`` (httpx handles serialization)
        - ``application/x-www-form-urlencoded`` → ``data=``
        - all other types (e.g. XML, plain text, binary) → ``content=``

        Args:
            method (str): The HTTP method (e.g., 'GET', 'POST').
            endpoint (str): The API endpoint path.
            params (Optional[dict]): A dictionary of URL query parameters. Defaults to None.
            extra_headers (Optional[dict]): A dictionary of additional HTTP headers.
                Defaults to None.
            content (Optional[RequestBodyContent]): The request body content.
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
            'GET': self._client.get,
            'POST': self._client.post,
            'PUT': self._client.put,
            'DELETE': self._client.delete
        }

        authorized_request = await self._authorizer.authorize(
            super()._build_request(
                method, endpoint, params, extra_headers, content, service_port
            )
        )
        content_type = _RestClientBase._resolve_content_type(authorized_request.headers)
        body_kwargs = _RestClientBase._build_body_kwargs(content_type, authorized_request.data)
        response: httpx.Response = await method_impls[authorized_request.method](
            url=authorized_request.url,
            headers=authorized_request.headers,
            params=authorized_request.params,
            **body_kwargs
        )

        return super()._process_response(response, response_type)


class RestClient(_RestClientBase):
    """Async Rest Client.

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
        super().__init__(service_url, service_port, api_prefix)
        self._authorizer = authorizer
        self._client = httpx.Client()

    def close(self):
        if self._client is not None:
            self._client.close()

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
        ResponseContentTypeDef: BaseModel
    ](
        self,
        response_type: Type[ResponseContentTypeDef],
        endpoint: str,
        query_params: Optional[dict] = None,
        content: Optional[RequestBodyContent] = None,
        headers: Optional[dict] = None,
        service_port: Optional[int] = None
    ) -> ResponseContentTypeDef:
        """Sends a POST request to create a resource.

        Args:
            response_type (Type[ResponseContentTypeDef]): The Pydantic model type
                to which the JSON response content should be deserialized.
            endpoint (str): The API endpoint path (e.g., "/items").
            query_params (Optional[Dict]): Mapping of URL query parameters
            content (Optional[RequestBodyContent]): The request body.
                Accepts a Pydantic BaseModel instance (serialized according to Content-Type),
                a raw ``str``, or raw ``bytes``. Defaults to None.
                When ``headers`` includes a ``Content-Type`` override, the body is serialized
                accordingly; otherwise defaults to JSON serialization.
            headers (Optional[dict]): A dictionary of additional HTTP headers to send.
                May include ``Content-Type`` to control body serialization and ``Accept``
                to control the expected response format. Defaults to None.
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
        self.__send_request(
            'DELETE',
            endpoint,
            extra_headers=headers,
            service_port=service_port
        )

    def __send_request[
        ResponseContentTypeDef: BaseModel
    ](
            self,
            method: str,
            endpoint: str,
            params: Optional[dict] = None,
            extra_headers: Optional[dict] = None,
            content: Optional[RequestBodyContent] = None,
            response_type: Optional[Type[ResponseContentTypeDef]] = None,
            service_port: Optional[int] = None
    ) -> Union[ResponseContentTypeDef, EmptyContent]:
        """Sends the actual HTTP request and processes the response.

        This private method selects the appropriate `requests` method based on
        the HTTP verb, builds the request, sends it, checks for HTTP errors,
        and deserializes the response content into the specified Pydantic model.

        The request body is dispatched to the correct httpx parameter based on
        the resolved Content-Type header:
        - ``application/json`` → ``json=`` (httpx handles serialization)
        - ``application/x-www-form-urlencoded`` → ``data=``
        - all other types (e.g. XML, plain text, binary) → ``content=``

        Args:
            method (str): The HTTP method (e.g., 'GET', 'POST').
            endpoint (str): The API endpoint path.
            params (Optional[dict]): A dictionary of URL query parameters. Defaults to None.
            extra_headers (Optional[dict]): A dictionary of additional HTTP headers.
                Defaults to None.
            content (Optional[RequestBodyContent]): The request body content.
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
            'GET': self._client.get,
            'POST': self._client.post,
            'PUT': self._client.put,
            'DELETE': self._client.delete
        }
        authorized_request = self._authorizer.authorize(
            super()._build_request(
                method, endpoint, params, extra_headers, content, service_port
            )
        )
        content_type = _RestClientBase._resolve_content_type(authorized_request.headers)
        body_kwargs = _RestClientBase._build_body_kwargs(content_type, authorized_request.data)
        response: httpx.Response = method_impls[authorized_request.method](
            url=authorized_request.url,
            headers=authorized_request.headers,
            params=authorized_request.params,
            **body_kwargs
        )

        return super()._process_response(response, response_type)


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
