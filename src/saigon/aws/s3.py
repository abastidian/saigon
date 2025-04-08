from typing import List, TypedDict, Unpack, Optional
from zipfile import ZipFile
from pathlib import Path
from tempfile import TemporaryDirectory
import logging
import os

from mypy_boto3_s3.client import S3Client
from aws_lambda_typing.events.s3 import S3 as S3EventData


class S3ObjectDescriptor(TypedDict):
    Bucket: str
    Key: str


def s3_object_descriptor_from_event(event: S3EventData) -> S3ObjectDescriptor:
    return dict(
        Bucket=event['bucket']['name'],
        Key=event['object']['key']
    )


def s3_object_to_file(
        s3_client: S3Client,
        **kwargs: Unpack[S3ObjectDescriptor]
) -> Path:
    file_object = s3_client.get_object(**kwargs)
    tmp_dir = TemporaryDirectory(delete=False)
    destination_filepath = Path.joinpath(Path(tmp_dir.name), kwargs['Key'])
    if not destination_filepath.parent.exists():
        os.makedirs(destination_filepath.parent)
    with open(destination_filepath, 'wb') as file_handle:
        logging.info(f"Save S3 object file to={destination_filepath}")
        file_handle.write(
            file_object['Body'].read()
        )

    return destination_filepath


def s3_object_unzip(
        s3_client: S3Client,
        **kwargs: Unpack[S3ObjectDescriptor]
) -> List[Path]:
    saved_zip_filepath = s3_object_to_file(
        s3_client, **kwargs
    )
    saved_zip_dir = saved_zip_filepath.parent
    with ZipFile(saved_zip_filepath, 'r') as zObject:
        zObject.extractall(
            path=saved_zip_dir
        )

    return [file for file in saved_zip_dir.iterdir() if file != saved_zip_filepath]


def s3_virtual_host_object_url(
        region: str,
        bucket: str,
        object_key: Optional[str] = None
) -> str:
    return (
        f"https://{bucket}.s3.{region}.amazonaws.com" + (f"/{object_key}" if object_key else "")
    )
