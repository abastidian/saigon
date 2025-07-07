import json
import logging
from functools import wraps
from pathlib import Path
from typing import Dict, Callable, Iterable, Type, List, Generator

from pydantic import BaseModel

import boto3
from mypy_boto3_s3.client import S3Client

from ...utils import EventHandler

__all__ = [
    'S3WriterHandler',
    'WriterHandlerInput',
    'HandlerInputContent',
    'write_to_s3',
    's3_writer_handler'
]

logger = logging.getLogger(__name__)


HandlerInputContent = BaseModel | Dict | str | Path


class WriterHandlerInput(BaseModel):
    bucket: str
    target_key: str
    content: HandlerInputContent


class S3WriterHandler(EventHandler[WriterHandlerInput, None]):
    def __init__(self):
        self._s3_client: S3Client = boto3.client('s3')

    def on_event(self, input_data: WriterHandlerInput):
        if isinstance(input_data.content, Path):
            logger.info(
                f"Upload input={input_data.content}"
                f" to dest={input_data.target_key}@{input_data.bucket}"
            )
            # upload file
            self._s3_client.upload_file(
                Filename=str(input_data.content),
                Bucket=input_data.bucket,
                Key=input_data.target_key
            )
        else:
            logger.info(
                f"Upload object of type={type(input_data.content)}"
                f" to dest={input_data.target_key}@{input_data.bucket}"
            )
            if isinstance(input_data.content, BaseModel):
                content = input_data.content.model_dump(
                    exclude_none=True
                )
            elif isinstance(input_data.content, List):
                content = json.dumps(
                    [
                        element.content.model_dump(exclude_none=True)
                        for element in input_data.content
                    ]
                )
            elif isinstance(input_data.content, Dict):
                content = json.dumps(input_data.content)
            else:
                content = input_data.content

            self._s3_client.put_object(
                Bucket=input_data.bucket,
                Key=input_data.target_key,
                Body=content.encode()
            )


def write_to_s3[InputData](
        bucket_name: str,
        object_keygen: Callable[[InputData, HandlerInputContent], str]
) -> Callable:

    def decorator(
            on_event: Callable[..., Iterable[HandlerInputContent]]
    ) -> Callable:
        s3_handler = S3WriterHandler()

        @wraps(on_event)
        def wrap_with_write(
                handler, input_data: InputData, **kwargs
        ) -> Generator[HandlerInputContent]:
            with on_event(handler, input_data, **kwargs) as result:
                s3_handler.on_event(
                    WriterHandlerInput(
                        bucket=bucket_name,
                        target_key=object_keygen(input_data, result),
                        content=result
                    )
                )
                return result

        return wrap_with_write

    return decorator


def s3_writer_handler[InputData](
        bucket_name: str,
        object_keygen: Callable[[InputData, HandlerInputContent], str]
) -> Callable[
    [Type[EventHandler]],
    Type[EventHandler]
]:
    def decorator(class_: Type[EventHandler]) -> Type[EventHandler]:
        if not issubclass(class_, EventHandler):
            raise ValueError(f"Invalid class={class_}: not an EventHandler")

        original_on_event = getattr(class_, 'on_event')

        # Replace the original 'on_event' with our wrapped version
        setattr(
            class_,
            'on_event',
            write_to_s3(bucket_name, object_keygen)(original_on_event)
        )
        return class_

    return decorator
