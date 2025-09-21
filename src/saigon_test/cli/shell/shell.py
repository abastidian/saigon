import uuid
import argparse
from typing import Optional, Type, TypeVar, Self, ClassVar, Dict

from prompt_toolkit.history import FileHistory

from shellody.shell import Shell
from shellody.shell import arguments

from saigon.utils import Environment
from saigon.aws.cognito import CognitoClientConfig
from saigon.rest.client import AuthRestClient
from saigon.model import ModelTypeDef

from .handlers import *

__all__ = [
    'RestClientTypeDef',
    'RestClientShellEnv',
    'RestClientShell'
]

RestClientTypeDef = TypeVar('RestClientTypeDef', bound=AuthRestClient)


class RestClientShellEnv(Environment):
    RCH_API_URL: str
    RCH_COGNITO_USER_POOL: str
    RCH_COGNITO_IDENTITY_POOL: str
    RCH_COGNITO_CLIENT_ID: str
    RCH_COGNITO_REGION: Optional[str] = None

    @property
    def cognito_config(self) -> CognitoClientConfig:
        return CognitoClientConfig(
            user_pool_id=self.RCH_COGNITO_USER_POOL,
            identity_pool_id=self.RCH_COGNITO_IDENTITY_POOL,
            client_id=self.RCH_COGNITO_CLIENT_ID,
            region=self.RCH_COGNITO_REGION
        )


class RestClientShell[RestClientTypeDef]:
    _COMMANDS_CONFIG = dict(
        prog=None,
        usage=None,
        add_help=True,
        conflict_handler='resolve'
    )
    _PROGRAM_ARG_SPEC = {
        'username': dict(
            flags=['-u', '--username'],
            help='Username for the default login',
            metavar='<username>'
        ),
        'password': dict(
            flags=['-p', '--password'],
            metavar='<password>'
        ),
        'history_path': dict(
            flags=['-s', '--history-path'],
            help='Set file path that contains the command history',
            nargs='?',
            default=None
        )
    }
    ResourceActionSpec: ClassVar = Dict[
        str,
        Dict[
            ModelTypeDef | ResourceHandlerFactory.MethodType,
            ResourceHandlerFactory.CreateHandlerSpec
        ],
    ]

    def __init__(
            self,
            program_name: str,
            shell_options: argparse.Namespace,
            cli_env: RestClientShellEnv,
            client_type: Type[RestClientTypeDef],
            **kwargs
    ):
        shell_config = dict(
            message=f"{program_name}>",
            history=FileHistory(shell_options.history_path),
            complete_while_typing=False,
            mouse_support=False,
            complete_in_thread=True
        )
        shell_commands = RestClientShell._COMMANDS_CONFIG.copy()
        shell_commands['prog'] = program_name
        self.shell = Shell(
            shell_commands, shell_config
        )
        self._client = client_type(
            cli_env.RCH_API_URL,
            cli_env.cognito_config,
            **kwargs
        )
        self._handler_factory = ResourceHandlerFactory(self._client)

        self._login_user_id: Optional[uuid.UUID] = None
        if shell_options.username:
            self._client.login(shell_options.username, shell_options.password)

    def register_actions(
            self, spec: ResourceActionSpec
    ) -> Self:
        for resource_name, resource_def in spec.items():
            resource_def = resource_def.copy()
            resource_type = resource_def.pop('type')
            for method, spec in resource_def.items():
                handler = self._handler_factory.create_handler(
                    resource_name, resource_type, method, **spec
                )
                command_name = (
                    f"{method.capitalize()}"
                    f"{resource_name.capitalize().replace('_', ' ')}"
                )
                self.shell.register_handler(
                    command_name,
                    handler,
                    handler.arg_spec(),
                    help=f"{method.capitalize()} "
                         f"{resource_name.capitalize().replace('_', ' ')}"
                )

        # built-in handlers
        handler = self._handler_factory.handler('login', 'get')
        self.shell.register_handler(
            handler.name.capitalize(),
            handler,
            argument_set=handler.arg_spec(),
            help='Login user'
        )

        return self

    def run(self):
        self.shell.run()

    @classmethod
    def build_arg_parser(cls, program_name: str, description: str) -> argparse.ArgumentParser:
        arg_parser = argparse.ArgumentParser(
            prog=program_name,
            usage=f"{program_name} [options]\nUse help or -h to see details",
            description=description,
            add_help=True
        )
        program_arg_spec = RestClientShell._PROGRAM_ARG_SPEC.copy()
        program_arg_spec['history_path']['default'] = f"./.history-{program_name}"
        arguments.add_parser_arguments(
            arg_parser, program_arg_spec
        )

        return arg_parser

    @classmethod
    def create_and_run[RestClientTypeDef](
            cls,
            program_name: str,
            description: str,
            shell_env: RestClientShellEnv,
            client_type: Type[RestClientTypeDef],
            resource_action_spec: ResourceActionSpec
    ):
        arg_parser = cls.build_arg_parser(program_name, description)
        RestClientShell(
            program_name,
            arg_parser.parse_args(),
            shell_env,
            client_type
        ).register_actions(
            resource_action_spec
        ).run()
