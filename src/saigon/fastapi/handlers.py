import logging
import abc
from typing import Generic, TypeVar, Optional, get_args, Any

from pydantic import BaseModel, model_validator

from fastapi import HTTPException, status

RequestType = TypeVar('RequestType', bound=BaseModel)
ResponseType = TypeVar('ResponseType', bound=BaseModel)

logger = logging.getLogger(__name__)


class EmptyRequestBody(BaseModel):
    pass


class EmptyResponseBody(BaseModel):
    @model_validator(mode='before')
    @classmethod
    def check_for_null(cls, data: Any) -> Any:
        if data is None:
            return {}

        return data


class RequestHandler(
    abc.ABC, Generic[RequestType, ResponseType]
):
    @abc.abstractmethod
    def _handle(self, *args, **kwargs) -> ResponseType:
        raise NotImplementedError

    def handle_request(
            self, request_body: Optional[RequestType | EmptyRequestBody] = None, *args, **kwargs
    ) -> ResponseType:
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
