from unittest.mock import Mock
from pydantic import BaseModel
from saigon.aws.secrets import AwsSecretVault, get_secret_as_model


class MySecret(BaseModel):
    user: str
    password: str


class TestAwsSecrets:
    def test_get_secret_as_model(self):
        mock_client = Mock()
        mock_client.get_secret_value.return_value = {
            'SecretString': '{"user": "u1", "password": "p1"}'
        }

        secret = get_secret_as_model(
            MySecret, "my-secret", mock_client
        )
        assert secret.user == "u1"
        assert secret.password == "p1"
        mock_client.get_secret_value.assert_called_once_with(
            SecretId="my-secret"
        )

    def test_aws_secret_vault(self):
        mock_client = Mock()
        vault = AwsSecretVault(secrets_client=mock_client)

        mock_client.get_secret_value.return_value = {
            'SecretString': '{"user": "u2", "password": "p2"}'
        }

        secret = vault.get_secret(MySecret, "my-secret-2")
        assert secret.user == "u2"
        mock_client.get_secret_value.assert_called_with(SecretId="my-secret-2")

        mock_client.get_secret_value.return_value = {
            'SecretString': 'plain-string'
        }
        assert vault.get_secret_string("plain-secret") == "plain-string"
