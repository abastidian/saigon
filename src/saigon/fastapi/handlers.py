import logging
import abc
from typing import Optional, get_args

from pydantic import BaseModel

from fastapi import HTTPException, status

from ..model import EmptyContent

__all__ = [
    'EmptyRequestBody',
    'EmptyResponseBody',
    'RequestHandler',
]

logger = logging.getLogger(__name__)

EmptyRequestBody = EmptyContent
EmptyResponseBody = EmptyContent


class RequestHandler[
    RequestType: BaseModel, ResponseType: BaseModel
](abc.ABC):
    """Abstract base class for handling incoming requests and generating responses.

    This generic class provides a structured way to define request handlers,
    enforcing types for both the incoming request body (`RequestType`) and
    the outgoing response body (`ResponseType`). It includes a central `handle_request`
    method that wraps the abstract `_handle` method, providing common logic
    for handling empty bodies, checking for `None` responses, and robust exception management.

    Type Variables:
        RequestType: A Pydantic `BaseModel` representing the structure of the
            incoming request body. Can be `EmptyRequestBody` if no body is expected.
        ResponseType: A Pydantic `BaseModel` representing the structure of the
            outgoing response body. Can be `EmptyResponseBody` if no content
            is expected in the response.
    """

    @abc.abstractmethod
    def _handle(self, *args, **kwargs) -> ResponseType:
        """Abstract method to be implemented by concrete request handlers.

        This method contains the core business logic for processing the request
        and generating the raw response. It should directly return an instance
        of `ResponseType`.

        Args:
            *args: Positional arguments passed to `handle_request`. The first
                argument is typically the `request_body`.
            **kwargs: Keyword arguments passed to `handle_request`.

        Returns:
            ResponseType: An instance of the defined response model.

        Raises:
            NotImplementedError: If the method is not overridden in a subclass.
        """
        raise NotImplementedError

    def handle_request(
            self,
            request_body: Optional[RequestType | EmptyRequestBody] = None,
            *args,
            **kwargs
    ) -> ResponseType:
        """
        Processes the incoming request, calls the internal handler, and manages responses.

        This method serves as a wrapper around the `_handle` method, providing:

        - Defaulting `request_body` to `EmptyRequestBody` if `None`.
        - Type checking to ensure the `_handle` method returns a non-None
          response if `ResponseType` is not `EmptyResponseBody`.
        - Centralized error handling for `HTTPException` and generic exceptions,
          mapping them to appropriate HTTP status codes.

        Args:
            request_body (Optional[RequestType | EmptyRequestBody]): The incoming
                request body, an instance of `RequestType` or `EmptyRequestBody`.
                Defaults to `None`, in which case `EmptyRequestBody()` is used.
            *args: Positional arguments to pass to the `_handle` method.
            **kwargs: Keyword arguments to pass to the `_handle` method.

        Returns:
            ResponseType: The processed response, an instance of `ResponseType`.

        Raises:
            HTTPException:
                - If `_handle` returns `None` and the expected `ResponseType` is not
                  `EmptyResponseBody` (raises `HTTP_404_NOT_FOUND`).
                - If a generic `Exception` occurs during `_handle` execution
                  (raises `HTTP_500_INTERNAL_SERVER_ERROR`).
                - If `_handle` itself raises an `HTTPException`.
        """
        handler_class = next(filter(
            lambda cls: cls.__name__ == RequestHandler.__name__,
            getattr(self.__class__, '__orig_bases__')
        ))
        response_type = get_args(handler_class)[1]
        try:
            result = self._handle(
                request_body if request_body else EmptyRequestBody(),
                *args,
                **kwargs
            )
            if result is None and response_type is not EmptyResponseBody:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail='resource not found'
                )

            return result
        except HTTPException:
            logger.exception('HTTP exception')
            raise
        except Exception:
            logger.exception('Generic exception')
            raise HTTPException(status_code=500, detail='error processing the request')