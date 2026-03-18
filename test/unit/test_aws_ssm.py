from unittest.mock import Mock
from pydantic import BaseModel
from saigon.aws.ssm import (
    AwsSsmVault, get_parameter_as_model, get_parameter_mapping_as_model
)


class MyModel(BaseModel):
    key1: str
    key2: str


class TestAwsSsm:
    def test_get_parameter_as_model(self):
        mock_client = Mock()
        mock_client.get_parameter.return_value = {
            'Parameter': {'Value': '{"key1": "v1", "key2": "v2"}'}
        }

        res = get_parameter_as_model(MyModel, "p1", ssm_client=mock_client)
        assert res.key1 == "v1"
        mock_client.get_parameter.assert_called_once_with(
            Name="p1", WithDecryption=False
        )

    def test_get_parameter_mapping_as_model(self):
        mock_client = Mock()
        mock_client.get_parameters.return_value = {
            'Parameters': [
                {'Name': 'ssm_p1', 'Value': 'v1'},
                {'Name': 'ssm_p2', 'Value': 'v2'}
            ]
        }

        mapping = {'ssm_p1': 'key1', 'ssm_p2': 'key2'}
        res = get_parameter_mapping_as_model(
            MyModel, mapping, ssm_client=mock_client
        )
        assert res.key1 == "v1"
        assert res.key2 == "v2"
        mock_client.get_parameters.assert_called_once()

    def test_aws_ssm_vault(self):
        mock_client = Mock()
        vault = AwsSsmVault(ssm_client=mock_client)

        mock_client.get_parameter.return_value = {
            'Parameter': {'Value': '{"key1": "v1", "key2": "v2"}'}
        }
        res = vault.get_secret(MyModel, "p1")
        assert res.key1 == "v1"

        mock_client.get_parameter.return_value = {
            'Parameter': {'Value': 'plain'}
        }
        assert vault.get_secret_string("p2") == "plain"
