import sys
import argparse
from typing import Optional
from pprint import pprint

from saigon.aws.cognito import CognitoClient, CognitoClientConfig
from saigon.utils import Environment


class CognitoCliEnv(Environment):
    COGNITO_USER_POOL_ID: Optional[str] = None
    COGNITO_IDENTITY_POOL_ID: Optional[str] = None
    COGNITO_CLIENT_ID: Optional[str] = None
    AWS_REGION: Optional[str] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class CognitoCliParams(CognitoClientConfig):
    command: str


class CognitoCli:

    def __init__(self, cli_params: CognitoCliParams):
        self._client = CognitoClient(cli_params)
        self._cli_params = cli_params

    def _handle_login(self, parse_args: argparse.Namespace):
        auth_result = self._client.login_user(
            parse_args.username, parse_args.password
        )
        print('Client successfully logged in with id token:')
        pprint(auth_result, indent=1)

        identity_creds = self._client.get_iam_credentials(
            auth_result['IdToken']
        )
        print('Retrieved identity credentials:')
        pprint(identity_creds, indent=1)

    def _handle_create_user(self, parse_args: argparse.Namespace):
        user_id, already_exists = self._client.create_user(
            parse_args.username,
            parse_args.notify,
            parse_args.self_verify,
            parse_args.group_name
        )
        if already_exists:
            pprint(f"User '{parse_args.username}' already exists")
        else:
            pprint(f"Created user '{parse_args.username}' with id={user_id}")

    def handle_command(self, parse_args: argparse.Namespace):
        command_actions = {
            'login': self._handle_login,
            'create-user': self._handle_create_user
        }
        command_actions[self._cli_params.command](parse_args)


def main():
    # load env
    cli_env = CognitoCliEnv()

    # Create parser
    parser = argparse.ArgumentParser(
        prog='cognito',
        usage='cognito-cli [options]\nUse help or -h to see details',
        description='Command line utility to aid with identity management operations',
        add_help=True
    )
    parser.add_argument(
        '-U', '--user-pool-id',
        default=cli_env.COGNITO_USER_POOL_ID,
        help='Set the target USER_POOL id. Overwrites env[COGNITO_USER_POOL_ID]'
    )
    parser.add_argument(

        '-I', '--identity-pool-id',
        default=cli_env.COGNITO_IDENTITY_POOL_ID,
        help='Set the target IDENTITY_POOL id. Overwrites env[COGNITO_IDENTITY_POOL_ID]'
    )
    parser.add_argument(
        '-C', '--client-id',
        default=cli_env.COGNITO_CLIENT_ID,
        help='Set the CLIENT id to act on behalf of. Overwrites env[COGNITO_CLIENT_ID]'
    )
    parser.add_argument(
        '--region',
        default=cli_env.AWS_REGION,
        help='Region where Cognito\'s pool are located'
    )

    subparsers = parser.add_subparsers(dest='command', required=True)
    subcommand_aliases = {
        'login': ['lo', 'lg'],
        'create-user': ['cu', 'ct']
    }

    # login command
    subcommand = 'login'
    parser_login = subparsers.add_parser(
        subcommand,
        aliases=subcommand_aliases[subcommand],
        help='logins as the specified user',
    )
    parser_login.add_argument('-u', '--username', required=True)
    parser_login.add_argument('-p', '--password', required=True)

    # create-user command
    subcommand = 'create-user'
    parser_create = subparsers.add_parser(
        subcommand,
        aliases=subcommand_aliases[subcommand],
        help='Creates the user given by its username and options',
    )
    parser_create.add_argument('-u', '--username')
    parser_create.add_argument(
        '--notify', action='store_true', default=False
    )
    parser_create.add_argument(
        '--self-verify', action='store_true', default=True
    )
    parser_create.add_argument(
        '-g', '--group-name', default=None
    )

    # Parse args
    args = parser.parse_args()
    for subcommand, aliases in subcommand_aliases.items():
        if args.command in aliases:
            args.command = subcommand

    try:
        for arg_name in ['user_pool_id', 'identity_pool_id', 'client_id']:
            if args.__getattribute__(arg_name) is None:
                raise ValueError(
                    f"A value for {arg_name.replace('_', '-')} must be be specified"
                )

        client = CognitoCli(CognitoCliParams(**vars(args)))
        client.handle_command(args)

    except Exception as exc:
        print(f"Error: {exc}")


if __name__ == '__main__':
    sys.exit(main())
