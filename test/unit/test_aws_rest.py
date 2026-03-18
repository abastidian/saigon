import uuid
from unittest.mock import Mock, patch
from requests import Request
from saigon.aws.rest import SIGv4RequestAuthorizer


class TestSigV4RequestAuthorizer:
    @patch('saigon.aws.rest.jwt')
    def test_login(self, mock_jwt):
        mock_cognito = Mock()
        mock_cognito.login_user.return_value = {'IdToken': 'dummy_token'}
        mock_cognito.get_iam_credentials.return_value = {
            'AccessKeyId': 'ak',
            'SecretKey': 'sk',
            'SessionToken': 'st'
        }
        user_id = str(uuid.uuid4())
        mock_jwt.decode.return_value = {'sub': user_id}

        auth = SIGv4RequestAuthorizer(mock_cognito)
        creds = auth.login("user", "pass")

        assert creds.access_key == "ak"
        assert creds.user_id == uuid.UUID(user_id)
        assert auth._current_user == "user"

    @patch('saigon.aws.rest.SigV4Auth')
    @patch('saigon.aws.rest.AWSRequest')
    def test_authorize(self, mock_aws_req, mock_sigv4_auth):
        mock_cognito = Mock()
        mock_cognito.aws_region = "us-east-1"
        auth = SIGv4RequestAuthorizer(mock_cognito)

        user_id = uuid.uuid4()
        auth._current_user = "user"
        from saigon.aws.rest import SigV4Credentials
        auth._logins["user"] = SigV4Credentials(
            AccessKeyId="ak", SecretKey="sk",
            SessionToken="st", user_id=user_id
        )

        req = Request(
            method="GET", url="https://api.example.com/test", headers={}
        )
        signed_req = auth.authorize(req)

        mock_sigv4_auth.assert_called_once()
        assert isinstance(signed_req, Request)
