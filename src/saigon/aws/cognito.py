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
    user_pool_id: str
    region: Optional[str] = None


class CognitoIdp:
    def __init__(self, config: CognitoIdpConfig):
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
            self._idp_client.admin_add_user_to_group(
                UserPoolId=self._config.user_pool_id,
                Username=username,
                GroupName=group_name
            )

        for attr in user_attributes:
            if attr['Name'] == 'sub':
                return uuid.UUID(attr['Value']), already_exists

        return uuid.UUID(username), already_exists

    def delete_user(self, username: str) -> bool:
        try:
            self._idp_client.admin_delete_user(
                UserPoolId=self._config.user_pool_id,
                Username=username,
            )
            return True
        except self._idp_client.exceptions.UserNotFoundException:
            return False

    def confirm_user(self, email: str):
        self._idp_client.admin_confirm_sign_up(
            UserPoolId=self._config.user_pool_id,
            Username=email
        )

    @cached_property
    def aws_region(self) -> str:
        return self._idp_client.meta.region_name


class CognitoClientConfig(CognitoIdpConfig):
    identity_pool_id: str
    client_id: str


class CognitoClient(CognitoIdp):
    def __init__(self, config: CognitoClientConfig):
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
        return (
            f"cognito-idp.{self._identity_client.meta.region_name}.amazonaws.com"
            f"/{self._config.user_pool_id}"
        )
