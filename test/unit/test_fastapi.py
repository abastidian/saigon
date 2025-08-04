import pytest
import uuid
import logging
from base64 import urlsafe_b64decode

from fastapi import background, status

from saigon.fastapi.headers import *
from saigon.fastapi.utils import *

CustomRequestContextTest = custom_request_context(
    'CustomRequestContext',
    'custom_idd',
    'custom_rid'
)
CustomRequestContextTestDependency = RouteContext.create_dependency(
    CustomRequestContextTest
)

CustomValidatorRequestContextTest = custom_request_context(
    'CustomValidatorRequestContextTest',
    'custom_idd',
    'custom_rid',
    lambda val: val.split(':')[0],
    lambda val: val
)

logger = logging.getLogger(__name__)


class TestRequestContext:
    @pytest.mark.parametrize(
        'identity_id, request_id',
        [
            pytest.param('my_custom_id', None),
            pytest.param('my_custom_id', str(uuid.uuid4())),
            pytest.param(uuid.uuid4(), None)
        ]
    )
    def test_default_context(
            self,
            identity_id,
            request_id
    ):
        init_params = {'identity_id': identity_id}
        if request_id:
            init_params['request_id'] = request_id

        context = HeaderContext(**init_params)
        assert context.identity_id == identity_id
        if request_id:
            assert context.request_id == request_id
        else:
            assert uuid.UUID(bytes=urlsafe_b64decode(context.request_id.encode()))

        assert context.headers == {
            DEFAULT_IDENTITY_ID_HEADER_NAME: str(context.identity_id),
            DEFAULT_API_REQUEST_ID_HEADER_NAME: context.request_id
        }

    def test_default_context_create_from_identity(self):
        identity_id = uuid.uuid4()
        context = HeaderContext.from_identity_id(identity_id)
        assert context.identity_id == identity_id

    def test_custom_context(self):
        context = CustomRequestContextTest(
            identity_id='test'
        )
        assert context.headers == {
            'custom_idd': str(context.identity_id),
            'custom_rid': context.request_id
        }

    def test_custom_validator_context(self):
        context = CustomValidatorRequestContextTest(
            identity_id='test_id:test_scope'
        )
        assert context.headers == {
            'custom_idd': str(context.identity_id),
            'custom_rid': context.request_id
        }


class TestAppContext:
    @pytest.mark.parametrize(
        'context_type, factory',
        [
            (HeaderContext, DefaultRouteContextDependency),
            (CustomRequestContextTest, CustomRequestContextTestDependency)
        ]
    )
    @pytest.mark.asyncio
    async def test_dependency_creation(
        self, context_type, factory
    ):
        context = await factory.dependency(
            background.BackgroundTasks(),
            context_type(identity_id=uuid.uuid4())
        )
        auto_context = route_context()
        assert isinstance(auto_context.header_context, context_type)
        assert context == auto_context
        assert context.headers == auto_context.headers

    @pytest.mark.parametrize(
        'context_type, factory',
        [
            (HeaderContext, DefaultRouteContextDependency),
            (CustomRequestContextTest, CustomRequestContextTestDependency)
        ]
    )
    def test_default_dependency_injection(
            self,
            empty_test_api,
            test_api_route,
            test_api_route_handler,
            empty_api_test_client,
            context_type,
            factory
    ):
        empty_test_api.include_router(
            test_api_route,
            dependencies=[factory]
        )
        # Invoke and check context
        response = empty_api_test_client.get(
            '/test',
            headers=context_type(identity_id='test_id').headers
        )
        assert response.status_code == status.HTTP_200_OK, response.content
        assert test_api_route_handler.app_context
        assert isinstance(
            test_api_route_handler.app_context.header_context, context_type
        )


class TestLogMiddleware:
    @pytest.mark.parametrize(
        'context_type, factory',
        [
            (HeaderContext, DefaultRouteContextDependency),
            (CustomRequestContextTest, CustomRequestContextTestDependency)
        ]
    )
    def test_header_context(
            self,
            empty_test_api,
            test_api_route,
            test_api_route_handler,
            empty_api_test_client,
            context_type,
            factory
    ):
        empty_test_api.add_middleware(
            LogMiddleware, logger=logger, context_type=context_type
        )
        empty_test_api.include_router(
            test_api_route, dependencies=[factory]
        )
        # Invoke and check context
        header_context = context_type(identity_id='test_id')
        response = empty_api_test_client.get(
            '/test',
            headers=header_context.headers
        )
        assert response.status_code == status.HTTP_200_OK, response.content
        assert test_api_route_handler.lc_items == header_context.model_dump(by_alias=False)

    def test_empty_header_contenxt(
            self,
            empty_test_api,
            test_api_route,
            test_api_route_handler,
            empty_api_test_client,
    ):
        empty_test_api.add_middleware(
            LogMiddleware, logger=logger
        )
        empty_test_api.include_router(test_api_route)
        # Invoke and check context
        response = empty_api_test_client.get('/test')
        assert response.status_code == status.HTTP_200_OK, response.content
        assert test_api_route_handler.lc_items == {}
        assert test_api_route_handler.empty_app_context
