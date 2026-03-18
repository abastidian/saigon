import pytest
from pydantic import BaseModel
from fastapi import HTTPException, status
from saigon.fastapi.handlers import (
    RequestHandler, EmptyRequestBody, EmptyResponseBody
)


class MyRequest(BaseModel):
    data: str


class MyResponse(BaseModel):
    result: str


class ConcreteHandler(RequestHandler[MyRequest, MyResponse]):
    def _handle(self, request_body: MyRequest) -> MyResponse:
        if request_body.data == "fail":
            raise ValueError("bad data")
        if request_body.data == "none":
            return None
        return MyResponse(result=f"processed {request_body.data}")


class EmptyHandler(RequestHandler[EmptyRequestBody, EmptyResponseBody]):
    def _handle(self, request_body: EmptyRequestBody) -> EmptyResponseBody:
        return EmptyResponseBody()


class TestFastAPIHandlers:
    def test_handle_request_success(self):
        handler = ConcreteHandler()
        response = handler.handle_request(MyRequest(data="test"))
        assert response.result == "processed test"

    def test_handle_request_none_returns_404(self):
        handler = ConcreteHandler()
        with pytest.raises(HTTPException) as excinfo:
            handler.handle_request(MyRequest(data="none"))
        assert excinfo.value.status_code == status.HTTP_404_NOT_FOUND

    def test_handle_request_exception_returns_500(self):
        handler = ConcreteHandler()
        with pytest.raises(HTTPException) as excinfo:
            handler.handle_request(MyRequest(data="fail"))
        assert (
            excinfo.value.status_code ==
            status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    def test_empty_handler(self):
        handler = EmptyHandler()
        response = handler.handle_request()
        assert isinstance(response, EmptyResponseBody)

    def test_deep_generic_inheritance(self):
        class MyBase[T](RequestHandler[T, MyResponse]):
            pass

        class MySub(MyBase[MyRequest]):
            def _handle(self, request_body: MyRequest) -> MyResponse:
                return MyResponse(result="ok")

        handler = MySub()
        response = handler.handle_request(MyRequest(data="test"))
        assert response.result == "ok"
