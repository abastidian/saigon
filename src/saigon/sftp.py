import stat
import fnmatch
import tempfile
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Self, List, Optional

import paramiko

from .model import BaseModelNoExtra, TimeRange

__all__ = [
    'SftpCredentials',
    'SftpClient'
]


class SftpCredentials(BaseModelNoExtra):
    host: str
    port: int
    username: str
    password: str


class SftpClient:
    def __init__(self, credentials: SftpCredentials):
        self._transport = paramiko.Transport(
            (credentials.host, credentials.port)
        )
        self._transport.connect(
            username=credentials.username, password=credentials.password
        )
        self._client = paramiko.SFTPClient.from_transport(self._transport)

    def list_files(
            self,
            remote_dir_path: Optional[str] = ".",
            date_range: Optional[TimeRange] = None,
            pattern: Optional[str | None] = None
    ) -> List:
        filtered = []

        for attr in self._client.listdir_attr(remote_dir_path):
            if attr.st_mode is not None and stat.S_ISDIR(attr.st_mode):
                continue
            if pattern and not fnmatch.fnmatch(attr.filename, pattern):
                continue

            if date_range and not (
                    date_range.start.timestamp() <= attr.st_mtime <= date_range.end.timestamp()
            ):
                continue

            filtered.append(attr.filename)

        return filtered

    @contextmanager
    def download(self, remote_path: str):
        with tempfile.NamedTemporaryFile(
                prefix=Path(remote_path).stem
        ) as temp_file:
            self._client.get(remote_path, temp_file.name)
            yield temp_file

    def close(self):
        if self._client:
            self._client.close()
        if self._transport:
            self._transport.close()

    @classmethod
    @contextmanager
    def client(cls, credentials: SftpCredentials) -> Generator[Self]:
        sftp_client = None
        try:
            sftp_client = SftpClient(credentials)
            yield sftp_client
        finally:
            if sftp_client:
                sftp_client.close()
