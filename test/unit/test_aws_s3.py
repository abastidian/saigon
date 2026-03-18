import shutil
from pathlib import Path
from unittest.mock import Mock, patch
from saigon.aws.s3 import (
    s3_object_to_file, s3_virtual_host_object_url,
    s3_object_descriptor_from_event
)


class TestAwsS3:
    def test_s3_object_to_file(self):
        mock_client = Mock()
        mock_body = Mock()
        mock_body.iter_chunks.return_value = [b"chunk1", b"chunk2"]
        mock_client.get_object.return_value = {'Body': mock_body}

        # We need to be careful with TemporaryDirectory(delete=False)
        # I'll mock it to control the directory
        with patch('saigon.aws.s3.TemporaryDirectory') as mock_tmp:
            import tempfile
            real_tmp = tempfile.mkdtemp()
            mock_tmp.return_value.name = real_tmp

            try:
                dest = s3_object_to_file(
                    mock_client, Bucket="b", Key="k/file.txt"
                )
                assert dest.name == "file.txt"
                assert dest.parent == Path(real_tmp) / "k"
                assert dest.read_bytes() == b"chunk1chunk2"
            finally:
                shutil.rmtree(real_tmp)

    def test_s3_virtual_host_object_url(self):
        url = s3_virtual_host_object_url("us-east-1", "my-bucket", "my-key")
        assert url == "https://my-bucket.s3.us-east-1.amazonaws.com/my-key"

        url_no_key = s3_virtual_host_object_url("us-east-1", "my-bucket")
        assert url_no_key == "https://my-bucket.s3.us-east-1.amazonaws.com"

    def test_s3_object_descriptor_from_event(self):
        event = {
            'bucket': {'name': 'my-bucket'},
            'object': {'key': 'my-key'}
        }
        desc = s3_object_descriptor_from_event(event)
        assert desc == {'Bucket': 'my-bucket', 'Key': 'my-key'}
