import uuid
from unittest.mock import Mock, patch
from saigon.aws.cognito import (
    get_user_pool_identity_from_iam_auth_provider,
    CognitoIdp, CognitoIdpConfig
)


def test_get_user_pool_identity_from_iam_auth_provider():
    user_id = str(uuid.uuid4())
    header = (
        f"cognito-idp.us-east-1.amazonaws.com/userpool,"
        f"cognito-idp.us-east-1.amazonaws.com/userpool:CognitoSignIn:{user_id}"
    )
    assert get_user_pool_identity_from_iam_auth_provider(header) == uuid.UUID(user_id)


class TestCognitoIdp:
    @patch('boto3.client')
    def test_create_user_new(self, mock_boto):
        mock_idp = Mock()
        mock_boto.return_value = mock_idp

        # Mock UserNotFoundException
        mock_idp.exceptions.UserNotFoundException = Exception  # Simplified
        mock_idp.admin_get_user.side_effect = Exception("UserNotFound")

        user_sub = str(uuid.uuid4())
        mock_idp.admin_create_user.return_value = {
            'User': {
                'Username': 'testuser',
                'Attributes': [{'Name': 'sub', 'Value': user_sub}]
            }
        }

        config = CognitoIdpConfig(user_pool_id="pool1", region="us-east-1")
        idp = CognitoIdp(config)

        sub, exists = idp.create_user("test@example.com")
        assert sub == uuid.UUID(user_sub)
        assert exists is False
        mock_idp.admin_create_user.assert_called_once()

    @patch('boto3.client')
    def test_delete_user(self, mock_boto):
        mock_idp = Mock()
        mock_boto.return_value = mock_idp

        config = CognitoIdpConfig(user_pool_id="pool1")
        idp = CognitoIdp(config)

        idp.delete_user("testuser")
        mock_idp.admin_delete_user.assert_called_once_with(
            UserPoolId="pool1", Username="testuser"
        )
