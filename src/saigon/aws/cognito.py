import uuid
from typing import Tuple, Optional, Dict, List
from functools import cached_property
from types import MappingProxyType

import boto3
from mypy_boto3_cognito_identity.type_defs import CredentialsTypeDef
from mypy_boto3_cognito_idp.type_defs import (
    AuthenticationResultTypeTypeDef, AttributeTypeTypeDef
)
from mypy_boto3_cognito_idp.client import CognitoIdentityProviderClient
from mypy_boto3_cognito_identity.client import CognitoIdentityClient

from pydantic import BaseModel


class CognitoIdpConfig(BaseModel):
    """Configuration for a Cognito Identity Provider (IdP) client.

    Attributes:
        user_pool_id (str): The ID of the Cognito User Pool.
        region (Optional[str]): The AWS region where the User Pool is located.
            If None, the default boto3 region will be used.
    """
    user_pool_id: str
    region: Optional[str] = None


class CognitoIdp:
    """Client for interacting with AWS Cognito Identity Provider (User Pools).

    This class provides methods for managing users within a Cognito User Pool,
    such as creating, deleting, and confirming users.
    """
    def __init__(self, config: CognitoIdpConfig):
        """Initializes the CognitoIdp client.

        Args:
            config (CognitoIdpConfig): Configuration settings for the Cognito User Pool.
        """
        self._config = config
        self._idp_client: CognitoIdentityProviderClient = boto3.client(
            'cognito-idp',
            region_name=config.region
        )

    def create_user(
            self,
            username_or_alias: str,
            notify_user: bool = True,
            self_verify: bool = False,
            group_name: str = None,
            temporary_password: str = None,
            extra_user_attrs: Dict = MappingProxyType({})
    ) -> Tuple[uuid.UUID, bool]:
        """Creates a new user in the Cognito User Pool or retrieves an existing one.

        If the user already exists, their UUID is returned along with `True` for `already_exists`.
        Otherwise, a new user is created with the specified attributes.
        The user can optionally be added to a group and have a temporary password set.

        Args:
            username_or_alias (str): The username or email alias for the user.
            notify_user (bool): If True, Cognito sends a welcome message to the user.
                If False, message sending is suppressed. Defaults to True.
            self_verify (bool): If True, the user's email is marked as verified.
                Defaults to False.
            group_name (str): The name of the Cognito group to which the user should be added.
                Defaults to None.
            temporary_password (str): A temporary password for the new user. If None,
                Cognito generates one (and sends it if `notify_user` is True). Defaults to None.
            extra_user_attrs (Dict): A dictionary of additional user attributes (e.g., 'given_name', 'family_name').
                Defaults to an empty immutable mapping.

        Returns:
            Tuple[uuid.UUID, bool]: A tuple where the first element is the UUID of the user,
                and the second element is a boolean indicating whether the user already existed (True)
                or was newly created (False).
        """
        already_exists = False
        try:
            response = self._idp_client.admin_get_user(
                UserPoolId=self._config.user_pool_id,
                Username=username_or_alias
            )
            already_exists = True
            username = response['Username']
            user_attributes = response['UserAttributes']

        except self._idp_client.exceptions.UserNotFoundException:
            extra_options = {}
            if not notify_user:
                extra_options['MessageAction'] = 'SUPPRESS'
            if temporary_password:
                extra_options['TemporaryPassword'] = temporary_password

            user_attributes: List[AttributeTypeTypeDef] = [
                {
                    'Name': 'email',
                    'Value': username_or_alias,
                },
                {
                    'Name': 'email_verified',
                    'Value': "true" if self_verify else "false"
                }
            ]
            user_attributes.extend([
                AttributeTypeTypeDef(
                    **{
                        'Name': attr,
                        'Value': value
                    }
                ) for attr, value in extra_user_attrs.items()
            ])

            response = self._idp_client.admin_create_user(
                UserPoolId=self._config.user_pool_id,
                Username=username_or_alias,
                UserAttributes=user_attributes,
                **extra_options
            )
            username = response['User']['Username']
            user_attributes = response['User']['Attributes']

            # Assign user to group
            if group_name: # Added check for group_name
                self._idp_client.admin_add_user_to_group(
                    UserPoolId=self._config.user_pool_id,
                    Username=username,
                    GroupName=group_name
                )

        for attr in user_attributes:
            if attr['Name'] == 'sub':
                return uuid.UUID(attr['Value']), already_exists

        # Fallback if 'sub' attribute is not found, use username as UUID (less common for real UUID)
        return uuid.UUID(username), already_exists

    def delete_user(self, username: str) -> bool:
        """Deletes a user from the Cognito User Pool.

        Args:
            username (str): The username of the user to delete.

        Returns:
            bool: True if the user was successfully deleted, False if the user was not found.
        """
        try:
            self._idp_client.admin_delete_user(
                UserPoolId=self._config.user_pool_id,
                Username=username,
            )
            return True
        except self._idp_client.exceptions.UserNotFoundException:
            return False

    def confirm_user(self, email: str):
        """Confirms a user's sign-up in the Cognito User Pool.

        This action is typically used by administrators to bypass the email
        verification step for a user.

        Args:
            email (str): The email (which serves as username) of the user to confirm.
        """
        self._idp_client.admin_confirm_sign_up(
            UserPoolId=self._config.user_pool_id,
            Username=email
        )

    @cached_property
    def aws_region(self) -> str:
        """Returns the AWS region associated with this Cognito IdP client.

        Returns:
            str: The AWS region name.
        """
        return self._idp_client.meta.region_name


class CognitoClientConfig(CognitoIdpConfig):
    """Configuration for a full Cognito client, extending IdP configuration.

    Attributes:
        identity_pool_id (str): The ID of the Cognito Identity Pool.
        client_id (str): The Client ID associated with the User Pool app client.
    """
    identity_pool_id: str
    client_id: str


class CognitoClient(CognitoIdp):
    """Client for comprehensive interaction with AWS Cognito (User Pools and Identity Pools).

    This class extends `CognitoIdp` to add functionalities for user authentication
    (login) and obtaining temporary AWS IAM credentials from Identity Pools
    using the authenticated user's ID token.
    """
    def __init__(self, config: CognitoClientConfig):
        """Initializes the CognitoClient.

        Args:
            config (CognitoClientConfig): Configuration settings for both Cognito User Pool
                and Identity Pool.
        """
        super().__init__(config)
        self._identity_client: CognitoIdentityClient = boto3.client(
            'cognito-identity',
            region_name=config.region
        )

    def login_user(
            self,
            username: str,
            password: str,
            new_password: str | None = None
    ) -> AuthenticationResultTypeTypeDef:
        """Logs in a user to the Cognito User Pool.

        This method handles the user password authentication flow. If a NEW_PASSWORD_REQUIRED
        challenge is returned (e.g., for first-time login with a temporary password),
        it attempts to respond to that challenge.

        Args:
            username (str): The username of the user.
            password (str): The user's password.
            new_password (str | None): A new password required if the user's password needs to be changed
                (e.g., for a temporary password). If None and a new password is required,
                the original password is used again for the new password. Defaults to None.

        Returns:
            AuthenticationResultTypeTypeDef: A dictionary containing the authentication result,
                including ID, Access, and Refresh tokens if successful.
        """
        response = self._idp_client.initiate_auth(
            ClientId=self._config.client_id,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': username,
                'PASSWORD': password
            }
        )
        if response.get("ChallengeName", None) == "NEW_PASSWORD_REQUIRED":
            response = self._idp_client.respond_to_auth_challenge(
                ClientId=self._config.client_id,
                ChallengeName="NEW_PASSWORD_REQUIRED",
                Session=response["Session"],
                ChallengeResponses={
                    "USERNAME": username,
                    "NEW_PASSWORD": new_password if new_password else password
                },
            )

        return response['AuthenticationResult']

    def get_iam_credentials(self, id_token: str) -> CredentialsTypeDef:
        """Obtains temporary AWS IAM credentials for an authenticated user.

        This method first gets an Identity ID from the Cognito Identity Pool
        using the provided ID token, and then exchanges that Identity ID
        and ID token for temporary AWS IAM credentials.

        Args:
            id_token (str): The ID token obtained from a successful Cognito User Pool login.

        Returns:
            CredentialsTypeDef: A dictionary containing temporary AWS IAM credentials
                (AccessKeyId, SecretKey, SessionToken, Expiration).
        """
        identity_response = self._identity_client.get_id(
            IdentityPoolId=self._config.identity_pool_id,
            Logins={self.get_cognito_url: id_token}
        )
        identity_id = identity_response['IdentityId']

        credentials_response = self._identity_client.get_credentials_for_identity(
            IdentityId=identity_id,
            Logins={self.get_cognito_url: id_token
                    }
        )

        return credentials_response['Credentials']

    @cached_property
    def get_cognito_url(self):
        """Returns the Cognito URL string used for authentication in Identity Pool logins.

        This URL combines the region and user pool ID, forming the key required
        by Cognito Identity Pool when associating an ID token with an identity.

        Returns:
            str: The formatted Cognito URL.
        """
        return (
            f"cognito-idp.{self._identity_client.meta.region_name}.amazonaws.com"
            f"/{self._config.user_pool_id}"
        )