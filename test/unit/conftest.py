import pytest
from typing import Optional

from fastapi import APIRouter, FastAPI, BackgroundTasks
from fastapi.testclient import TestClient

from saigon.fastapi.handlers import RequestHandler, EmptyRequestBody, EmptyResponseBody
from saigon.fastapi.utils import RouteContext, route_context
from saigon.logutils import logcontext


class TestApiRouteHandler(RequestHandler[EmptyRequestBody, EmptyResponseBody]):
    __test__ = False

    def __init__(self):
        self.app_context: Optional[RouteContext] = None
        self.empty_app_context = False
        self.lc_items = {}

    def _handle(self, request: None, **kwargs):
        with logcontext() as lc:
            self.lc_items = lc.items()
        try:
            self.app_context = route_context()
        except LookupError:
            self.empty_app_context = True


@pytest.fixture(scope='function')
def test_api_route_handler() -> TestApiRouteHandler:
    return TestApiRouteHandler()


@pytest.fixture(scope='function')
def test_api_route(test_api_route_handler) -> APIRouter:
    api_router = APIRouter()

    @api_router.get('/test')
    def test_route():
        test_api_route_handler.handle_request()

    return api_router


@pytest.fixture(scope='function')
def empty_test_api() -> FastAPI:
    return FastAPI()


@pytest.fixture(scope='function')
def empty_api_test_client(empty_test_api) -> TestClient:
    return TestClient(empty_test_api)
