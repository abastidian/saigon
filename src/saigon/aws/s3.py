import logging
import os
from zipfile import ZipFile
from pathlib import Path
from tempfile import TemporaryDirectory
from io import BytesIO
from typing import List, TypedDict, Unpack, Optional

import boto3
from mypy_boto3_s3.client import S3Client
from aws_lambda_typing.events.s3 import S3 as S3EventData

__all__ = [
    's3_get_client',
    'S3ObjectDescriptor',
    's3_object_descriptor_from_event',
    's3_object_to_file',
    's3_object_unzip',
    's3_virtual_host_object_url'
]


class S3ObjectDescriptor(TypedDict):
    """A TypedDict representing the essential identifiers for an S3 object.

    Attributes:
        Bucket (str): The name of the S3 bucket.
        Key (str): The key (path) of the object within the bucket.
    """
    Bucket: str
    Key: str


def s3_get_client() -> S3Client:
    """Returns a Boto3 S3 client instance.

    Returns:
        S3Client: A Boto3 S3 client.
    """
    return boto3.client('s3')


def s3_object_to_file(
        s3_client: S3Client,
        **kwargs: Unpack[S3ObjectDescriptor]
) -> Path:
    """Downloads an S3 object to a temporary local file.

    The file is saved within a temporary directory created by this function.
    The path of the downloaded file is constructed from the temporary directory
    and the S3 object's key.

    Args:
        s3_client (S3Client): The Boto3 S3 client instance.
        **kwargs (Unpack[S3ObjectDescriptor]): Keyword arguments representing
            an `S3ObjectDescriptor`, typically containing 'Bucket' and 'Key'.

    Returns:
        Path: The `pathlib.Path` object pointing to the downloaded temporary file.
    """
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
    """Downloads and unzips an S3 object (assumed to be a ZIP file) to a temporary directory.

    The ZIP file is first downloaded using `s3_object_to_file`, and then its
    contents are extracted into the same temporary directory as the ZIP file.
    The original ZIP file itself is excluded from the returned list of paths.

    Args:
        s3_client (S3Client): The Boto3 S3 client instance.
        **kwargs (Unpack[S3ObjectDescriptor]): Keyword arguments representing
            an `S3ObjectDescriptor`, typically containing 'Bucket' and 'Key' of the ZIP file.

    Returns:
        List[Path]: A list of `pathlib.Path` objects for all files extracted from the ZIP archive.
    """
    saved_zip_filepath = s3_object_to_file(
        s3_client, **kwargs
    )
    saved_zip_dir = saved_zip_filepath.parent
    with ZipFile(saved_zip_filepath, 'r') as zObject:
        zObject.extractall(
            path=saved_zip_dir
        )

    return [file for file in saved_zip_dir.iterdir() if file != saved_zip_filepath]


def s3_write_bytes(
        s3_client: S3Client,
        bucket: str,
        key: str,
        target_bytes: BytesIO,
        content_type: str = 'application/octet-stream'
):
    """Uploads bytes from a BytesIO object to an S3 object.

    Args:
        s3_client (S3Client): The Boto3 S3 client instance.
        bucket (str): The name of the target S3 bucket.
        key (str): The key (path) of the object to create or overwrite in S3.
        target_bytes (BytesIO): A BytesIO object containing the data to upload.
        content_type (str): The Content-Type header for the S3 object.
            Defaults to 'application/octet-stream'.
    """
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=target_bytes,
        ContentType=content_type
    )


def s3_object_descriptor_from_event(event: S3EventData) -> S3ObjectDescriptor:
    """Extracts an S3 object descriptor from an AWS S3 event.

    This function parses a standard AWS S3 event payload (e.g., from Lambda)
    to retrieve the bucket name and object key.

    Args:
        event (S3EventData): The S3 event data dictionary, typically found
            within a Lambda event record.

    Returns:
        S3ObjectDescriptor: A dictionary containing the 'Bucket' name and 'Key' of the S3 object
            involved in the event.
    """
    return dict(
        Bucket=event['bucket']['name'],
        Key=event['object']['key']
    )


def s3_virtual_host_object_url(
        region: str,
        bucket: str,
        object_key: Optional[str] = None
) -> str:
    """Generates a virtual-hosted style URL for an S3 bucket or object.

    This format is `https://<bucket-name>.s3.<region>.amazonaws.com/<object-key>`.
    If `object_key` is not provided, it generates a URL for the bucket itself.

    Args:
        region (str): The AWS region of the S3 bucket.
        bucket (str): The name of the S3 bucket.
        object_key (Optional[str]): The key of the object within the bucket.
            Defaults to None.

    Returns:
        str: The generated virtual-hosted style URL.
    """
    return (
        f"https://{bucket}.s3.{region}.amazonaws.com" + (f"/{object_key}" if object_key else "")
    )