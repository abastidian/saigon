import logging
from datetime import datetime
from contextvars import ContextVar
from typing import Annotated, Optional, Self

from pydantic import ConfigDict, Field, ValidationError

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import (
    FastAPI, Query, Header, BackgroundTasks, Depends, status, Request, APIRouter
)
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse

from ..model import QueryDataParams, QueryDataPaginationToken
from ..logutils import asynclogcontext
from ..model import TimeRange

from .headers import *
from .handlers import EmptyResponseBody

__all__ = [
    'use_route_names_as_operation_ids',
    'LogMiddleware',
    'AppContext',
    'AppContextDependency',
    'app_context',
    'validate_query_pagination_params',
    'validate_query_date_range',
    'validation_error_exception_handler',
    'create_app'
]

_APP_CONTEXT = ContextVar('_APP_CONTEXT')


def use_route_names_as_operation_ids(app: FastAPI) -> None:
    """Simplifies FastAPI operation IDs by setting them to the route's name.

    This function iterates through all registered routes in a FastAPI application
    and, for `APIRoute` instances, sets their `operation_id` to their `name`.
    This helps in generating API clients with simpler and more readable function names.

    This function should be called only after all desired routes have been added to the FastAPI application.

    Args:
        app (FastAPI): The FastAPI application instance.
    """
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.operation_id = route.name  # in this case, 'read_items'


def validate_query_pagination_params(
        query_id: Annotated[str, Query(alias='QueryId')] = None,
        next_token: Annotated[str, Query(alias='NextToken')] = None,
        max_frame_count: Annotated[int, Query(alias='MaxCount', gt=0)] = None
) -> QueryDataParams:
    """Validates and constructs `QueryDataParams` from pagination query parameters.

    This dependency function processes optional `QueryId`, `NextToken`, and `MaxCount`
    query parameters, combining them into a `QueryDataParams` object suitable
    for pagination logic.

    Args:
        query_id (Annotated[str, Query], optional): The ID of a previous query for pagination.
            Corresponds to the 'QueryId' query parameter. Defaults to None.
        next_token (Annotated[str, Query], optional): The token for the next page of results.
            Corresponds to the 'NextToken' query parameter. Defaults to None.
        max_frame_count (Annotated[int, Query], optional): The maximum number of items to return
            in a single response. Must be greater than 0. Corresponds to the 'MaxCount'
            query parameter. Defaults to None.

    Returns:
        QueryDataParams: An object containing the parsed pagination parameters.
    """
    return QueryDataParams(
        max_count=max_frame_count,
        query=QueryDataPaginationToken(
            query_id=query_id,
            next_token=next_token
        ) if query_id and next_token else None
    )


def validate_query_date_range(
        start_time: Annotated[datetime, Query(alias='StartTime')] = None,
        end_time: Annotated[datetime, Query(alias='EndTime')] = None
) -> TimeRange | None:
    """Validates and constructs a `TimeRange` object from 'StartTime' and 'EndTime' query parameters.

    If both `start_time` and `end_time` are None, it returns None.
    If only `start_time` is provided, `end_time` defaults to the current UTC datetime.
    If only `end_time` is provided, `start_time` defaults to the Unix epoch (datetime.min).
    Otherwise, a `TimeRange` object is created with the provided or defaulted times.

    Args:
        start_time (Annotated[datetime, Query], optional): The start of the time range.
            Corresponds to the 'StartTime' query parameter. Defaults to None.
        end_time (Annotated[datetime, Query], optional): The end of the time range.
            Corresponds to the 'EndTime' query parameter. Defaults to None.

    Returns:
        TimeRange | None: A `TimeRange` object if either `start_time` or `end_time`
            is provided, otherwise None.
    """
    if start_time is None and end_time is None:
        return None

    if end_time is None:
        end_time = datetime.now()

    if start_time is None:
        start_time = datetime(
            year=1, month=1, day=1, hour=0, minute=0, microsecond=0
        )

    return TimeRange(
        start=start_time, end=end_time
    )


def validation_error_exception_handler(
        _: Request, exc: Exception
) -> JSONResponse:
    """Custom exception handler for Pydantic's `ValidationError`.

    This handler intercepts `ValidationError` instances, ensuring that they
    return a `422 Unprocessable Entity` HTTP response with structured error
    details, consistent with FastAPI's default Pydantic error responses.
    For any other exception type, it returns a generic `500 Internal Server Error`.

    Args:
        _ (Request): The incoming request object (unused).
        exc (Exception): The exception that was caught.

    Returns:
        JSONResponse: A FastAPI `JSONResponse` with an appropriate status code
            and error details.
    """
    # The 'errors()' method of ValidationError returns a list of dictionaries,
    # which is the standard format for FastAPI's 422 responses.
    if isinstance(exc, ValidationError):
        # The 'errors()' method of ValidationError returns a list of dictionaries,
        # which is the standard format for FastAPI's 422 responses.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
        )
    else:
        # If it's not a ValidationError, re-raise or handle as a generic 500 error.
        # For simplicity, we'll return a generic 500 here.
        # In a real app, you might want to log the unexpected exception.
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"{exc}"},
        )


class LogMiddleware(BaseHTTPMiddleware):
    """
    Middleware for FastAPI applications that enhances logging and request context.

    This middleware provides two main functionalities:

    1. Wraps the `dispatch` method with `asynclogcontext`, making a request-specific
       log context available for all endpoint implementations.
    2. Encloses the `call_next` call within log messages, indicating the reception
       and return of a request and response, respectively. It also populates
       the log context with `request_id` and `caller_id` from incoming headers.

    To use this middleware, add it to your FastAPI application:

    Example::

        app.add_middleware(LogMiddleware, logger=my_logger)
    """

    def __init__(self, app: FastAPI, logger: logging.Logger):
        """Initializes the LogMiddleware.

        Args:
            app (FastAPI): The FastAPI application instance.
            logger (logging.Logger): The logger instance to use for logging
                request and response information.
        """
        super().__init__(app)
        self._logger = logger

    async def dispatch(self, request: Request, call_next):
        """
        Dispatches the incoming request and processes the response.

        This method sets up an asynchronous log context, extracts request IDs
        and caller IDs from headers to populate the context, logs the start
        and end of the request processing, and passes control to the next
        middleware or endpoint.

        Args:
            request (Request): The incoming Starlette request object.
            call_next (Callable): The next callable in the middleware chain.

        Returns:
            Response: The Starlette response object.
        """
        async with asynclogcontext() as alc:
            if request_id := request.headers.get(AWS_API_REQUEST_ID_HEADER_NAME, None):
                alc.set(request_id=request_id)
            if identity_id := request.headers.get(AWS_COGNITO_IAM_AUTH_PROVIDER_HEADER_NAME):
                alc.set(caller_id=identity_id)

            self._logger.info(
                'Received request',
                extra=dict(
                    method=request.method,
                    url=str(request.url)
                )
            )

            response = await call_next(request)

            self._logger.info(
                'Return response',
                extra=dict(status_code=response.status_code)
            )

            return response


class AppContext(RequestContext):
    """
    Represents the application context for a given request.

    This class extends `RequestContext` by adding request-specific utilities
    like `BackgroundTasks` and makes the context globally accessible via a `ContextVar`.
    It is designed to be injected as a dependency into FastAPI routes.

    Attributes:
        background_tasks (Optional[BackgroundTasks]): FastAPI's `BackgroundTasks`
            instance, allowing tasks to be run after the HTTP response has been sent.
            This field is excluded from Pydantic models (e.g., when dumping to JSON).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    background_tasks: Optional[BackgroundTasks] = Field(None, exclude=True)

    def __init__(self, **kwargs):
        """Initializes the AppContext instance.

        Args:
            **kwargs: Keyword arguments passed to the parent `RequestContext` constructor,
                along with `background_tasks`.
        """
        super().__init__(**kwargs)

    @classmethod
    async def from_route(
            cls,
            background_tasks: BackgroundTasks,
            request_context: Annotated[RequestContext, Header()]
    ) -> Self:
        """Dependency function to create and set the `AppContext` for a given request.

        This class method is intended to be used with FastAPI's `Depends` system.
        It constructs an `AppContext` instance from injected `BackgroundTasks`
        and `RequestContext` (parsed from headers), and then sets this context
        in a `ContextVar` to make it globally accessible during the request lifetime.

        Args:
            background_tasks (BackgroundTasks): FastAPI's injected `BackgroundTasks` object.
            request_context (Annotated[RequestContext, Header()]): The request context
                parsed directly from HTTP headers by FastAPI.

        Returns:
            Self: The newly created and set `AppContext` instance.
        """
        _APP_CONTEXT.set(
            context := AppContext(
                background_tasks=background_tasks,
                **request_context.model_dump(by_alias=False)
            )
        )
        return context


AppContextDependency = Depends(AppContext.from_route)
"""A FastAPI dependency that injects and sets the `AppContext` for a request.

This dependency should be added to FastAPI route functions or `APIRouter`s
to ensure `AppContext` is available and configured for the request.
"""


def app_context() -> AppContext:
    """Retrieves the current application context from the ContextVar.

    This function provides a way to access the `AppContext` instance
    that was set up by `AppContext.from_route` for the current request.

    Returns:
        AppContext: The `AppContext` instance for the current request.
    """
    return _APP_CONTEXT.get()


def create_app(
        api_router: APIRouter,
        logger: logging.Logger,
        root_path: Optional[str] = '/v1',
        health_path: Optional[str | None] = '/',
        **kwargs
) -> FastAPI:
    """Factory function to create and configure a FastAPI application.

    This function sets up the basic FastAPI application, adds necessary middleware,
    registers exception handlers, includes the provided API router, and
    configures health check endpoints and operation ID simplification.

    Args:
        api_router (APIRouter): The API router containing all defined endpoints
            for the application.
        logger (logging.Logger): The logger instance to be used by the `LogMiddleware`.
        root_path (Optional[str]): The root path for the application. Defaults to '/v1'.
        health_path (Optional[str | None]): The path for the health check endpoint.
            If set to None, no health endpoint is added. Defaults to '/'.
        **kwargs: Additional keyword arguments to pass directly to the FastAPI constructor.

    Returns:
        FastAPI: The configured FastAPI application instance.
    """
    app = FastAPI(
        root_path=root_path, **kwargs
    )
    app.add_middleware(LogMiddleware, logger=logger)
    app.add_exception_handler(ValidationError, validation_error_exception_handler)
    app.include_router(api_router, dependencies=[AppContextDependency])
    if health_path:
        app.add_api_route(health_path, lambda: EmptyResponseBody())

    use_route_names_as_operation_ids(app)

    return app