import abc
import argparse
import json
import uuid
from typing import (
    List,
    Iterable,
    Type,
    override,
    Optional,
    TypeVar,
    Callable,
    Dict,
    Self,
    ClassVar,
    Unpack,
    Set,
    TypedDict,
    Literal
)

from prompt_toolkit.completion import Completion, WordCompleter
from shellody.shell import CommandHandler
from shellody.completion import CompletionContext, KeyValueCompleter

from pydantic import BaseModel

from saigon.model import ModelTypeDef, QueryDataPaginationToken
from saigon.model import QueryDataParams
from saigon.rest.client import AuthRestClient

__all__ = [
    'ResourceHandlerFactory',
    'BaseResourceHandler',
    'QueryResourceHandler',
    'CreateResourceHandler',
    'LoginHandler',
    'DeleteResourceHandler',
    'QuerySelectionTypeDef',
    'RequestBodyTypeDef',
    'ResponseBodyTypeDef'
]

QuerySelectionTypeDef = TypeVar('QuerySelectionTypeDef', bound=BaseModel)
RequestBodyTypeDef = TypeVar('RequestBodyTypeDef', bound=BaseModel)
ResponseBodyTypeDef = TypeVar('ResponseBodyTypeDef', bound=BaseModel)

ResourceHandlerInitParams = TypedDict(
    'ResourceHandlerInitParams',
    {
        'name': str,
        'resource_type': Type[ModelTypeDef],
        'query_type': Optional[Type[QuerySelectionTypeDef]],
        'request_type': Optional[Type[RequestBodyTypeDef]],
        'response_type': Optional[Type[RequestBodyTypeDef]],
        'parent': Optional[Self],
        'arg_value_provider': Optional[Callable[[str], Set]]
    }
)


class BaseResourceHandler[ResourceType](CommandHandler, abc.ABC):
    _QUERY_ARG_SPEC: ClassVar = {
        'query': dict(
            flags=['-q', '--query'],
            help='query expression',
            nargs='?',
            metavar='<query_exp>'
        )
    }
    _PARENT_ID_ARG_SPEC = {
        'parent_id': dict(
            flags=['-p', '--parent_id'],
            help='parent id',
            metavar='<parent_id>',
            required=True,
            type=uuid.UUID
        )
    }
    _ENTITY_ID_ARG_SPEC = {
        'id': dict(
            nargs='?',
            metavar='[<entity_id>]',
            type=uuid.UUID
        )
    }
    _DEFAULT_ID_ARG_SPEC = {
        'default_id': dict(
            flags=['-d', '--default_id'],
            action='store_true',
        )
    }

    def __init__(
            self,
            client: AuthRestClient,
            **kwargs: Unpack[ResourceHandlerInitParams]
    ):
        self._client = client
        self._name = kwargs['name']
        self._parent = kwargs.get('parent', None)
        self._entities: Set[ResourceType] = set()
        self._arg_value_provider = (
            arg_value_provider if (arg_value_provider := kwargs.get('arg_value_provider', None))
            else lambda _: set()
        )
        self._query_selection_type = kwargs.get('query_type', None)
        # Build the map of query parameters based on the specified selection type,
        # but always including the pagination token params
        self._query_max_count_option = {'max_count': 'int'}
        self._query_pagination_token_options = {
            name: info.annotation.__name__
            for name, info in QueryDataPaginationToken.model_fields.items()
        }
        self._query_selection_options = {
            name: info.annotation.__name__
            for name, info in self._query_selection_type.model_fields.items()
        } if self._query_selection_type else {}

        self._request_type = kwargs.get('request_type', None)
        self._response_type = kwargs.get('response_type', None)

    @property
    def name(self) -> str:
        return self._name

    @property
    def entities(self) -> Set[ResourceType]:
        return self._entities

    @property
    def entity_ids(self) -> Set[uuid.UUID]:
        fetched_ids = {entity.id for entity in self._entities}
        return fetched_ids | self._arg_value_provider('entity_id')

    def arg_spec(self) -> Dict[str, dict]:
        return {
            **(
                BaseResourceHandler._QUERY_ARG_SPEC if self._query_selection_type else {}
            ),
            **(
                BaseResourceHandler._PARENT_ID_ARG_SPEC if self._parent else {}
            )
        }

    @override
    def get_completions(self, context: CompletionContext) -> Iterable[Completion]:
        # Query completions
        if self._query_selection_type and context.arg_descriptor.name == 'query':
            current_query_options = context.word.split(',', 2)
            if (
                    current_query_options[0].startswith('max_count')
                    or current_query_options[0] == ''
            ):
                current_query_options.pop(0)

            first_current_option = (
                current_query_options[0].split('=')[0] if current_query_options
                else None
            )
            if first_current_option:
                if first_current_option in self._query_pagination_token_options.keys():
                    completion_query_options = dict(
                        self._query_max_count_option,
                        **self._query_pagination_token_options
                    )
                else:
                    completion_query_options = dict(
                        self._query_max_count_option,
                        **self._query_selection_options
                    )
            else:
                completion_query_options = dict(
                    self._query_max_count_option,
                    **self._query_selection_options,
                    **self._query_pagination_token_options
                )

            for completion in KeyValueCompleter(
                    list(completion_query_options.keys()), ['=']
            ).get_completions(context):
                yield completion

        # Parent or entity IDs completion
        if context.arg_descriptor.name == 'parent_id':
            entity_ids = self._parent.entity_ids
        elif context.arg_descriptor.name == 'id':
            entity_ids = self.entity_ids
            yield Completion(
                text='', display=BaseResourceHandler._ENTITY_ID_ARG_SPEC['id']['metavar']
            )
        else:
            entity_ids = []

        for completion in WordCompleter(
                [str(e_id) for e_id in entity_ids]
        ).get_completions(context.document, context.event):
            yield completion

    def _parse_query_selection(
            self, query_string: str
    ) -> QueryDataParams[QuerySelectionTypeDef]:
        assignments = query_string.split(',')
        selection_init = {}
        for param_assignment in assignments:
            name, value = param_assignment.split('=')
            selection_init[name] = value

        pagination_token_type = None
        for key in self._query_pagination_token_options:
            if key in selection_init:
                pagination_token_type = QueryDataPaginationToken
                break

        return QueryDataParams(
            max_count=selection_init.pop('max_count', None),
            query=(
                pagination_token_type(**selection_init) if pagination_token_type
                else self._query_selection_type(**selection_init)
            )
        )


class QueryResourceHandler[ResourceType](BaseResourceHandler[ResourceType]):
    def __init__(
            self,
            client: AuthRestClient,
            **kwargs: Unpack[ResourceHandlerInitParams]
    ):
        super().__init__(client, **kwargs)
        self._get_entity = getattr(self._client, f"get_{kwargs['name']}")
        self._query_entities = (
            query_function
            if (query_function := getattr(self._client, f"query_{kwargs['name']}s", None))
            else getattr(self._client, f"query_{kwargs['name']}", None)
        )

    @override
    def arg_spec(self) -> Dict[str, dict]:
        return {
            **super().arg_spec(),
            **(
                BaseResourceHandler._DEFAULT_ID_ARG_SPEC if self._arg_value_provider else {}
            ),
            **BaseResourceHandler._ENTITY_ID_ARG_SPEC
        }

    @override
    def handle(self, command_args: argparse.Namespace) -> Optional[dict]:
        # Build query data from argument when required
        query_data = (
            super()._parse_query_selection(command_args.query)
        ) if self._query_selection_type and command_args.query else None

        # Build entity id path from arguments
        path_id = [command_args.parent_id] if self._parent else []

        target_id = (
            command_args.id if command_args.id
            else (
                next(iter(self.entity_ids)) if command_args.default_id and self.entity_ids
                else None
            )
        )
        if target_id:
            path_id += [target_id]
            result = self._get_entity(*path_id)
            self._entities = [result]
        elif self._query_selection_type:
            result = self._query_entities(*path_id, query_data)
            self._entities = result.data
        else:
            raise ValueError('ambiguous operation: specify an entity ID or query')

        return result.model_dump(
            mode='json', exclude_none=True, exclude_unset=False
        )


class CreateResourceHandler[ResourceType](BaseResourceHandler[ResourceType]):
    _BODY_ARG_SPEC: ClassVar = {
        'body': dict(
            flags=['-b', '--body'],
            nargs='+',
            help='request body',
            metavar='<body_exp>'
        )
    }

    def __init__(
            self,
            client: AuthRestClient,
            **kwargs: Unpack[ResourceHandlerInitParams]
    ):
        super().__init__(client, **kwargs)
        self._create_entity = getattr(self._client, f"create_{kwargs['name']}")

    @override
    def arg_spec(self) -> Dict[str, dict]:
        return {
            **super().arg_spec(),
            **CreateResourceHandler._BODY_ARG_SPEC
        }

    @override
    def handle(self, command_args: argparse.Namespace) -> dict:
        path_id = [command_args.parent_id] if self._parent else []
        request_body = self._parse_body_expression(command_args.body)
        result = self._create_entity(
            *path_id, request_body
        )
        return result.model_dump(mode='json', exclude_none=True, exclude_unset=False)

    @override
    def get_completions(self, context: CompletionContext) -> Iterable[Completion]:
        if context.arg_descriptor.name == 'body':
            body_fields = [name for name, _ in self._request_type.model_fields.items()]
            return KeyValueCompleter(
                body_fields, [':']
            ).get_completions(context)

        return super().get_completions(context)

    def _parse_body_expression(self, body_expression: List[str]) -> RequestBodyTypeDef:
        body_string = ''
        for chunk in body_expression:
            body_string += chunk
        body_string = body_string.removeprefix('\'').removesuffix('\'')

        return self._request_type(
            **json.loads(body_string)
        )


class DeleteResourceHandler[ResourceType](BaseResourceHandler[ResourceType]):
    def __init__(
            self,
            client: AuthRestClient,
            **kwargs: Unpack[ResourceHandlerInitParams]
    ):
        super().__init__(client, **kwargs)
        self._delete_entity: Callable[..., ModelTypeDef] = getattr(
            self._client, f"delete_{kwargs['name']}"
        )

    @override
    def arg_spec(self) -> Dict[str, dict]:
        return {
            **super().arg_spec(),
            **BaseResourceHandler._ENTITY_ID_ARG_SPEC
        }

    @override
    def handle(
            self, command_args: argparse.Namespace
    ) -> Optional[dict]:
        self._delete_entity(command_args.id)
        return None


class LoginHandler(BaseResourceHandler[dict]):
    def __init__(
            self,
            client: AuthRestClient
    ):
        super().__init__(
            client,
            name='login',
            resource_type=dict
        )

    @override
    def arg_spec(self) -> Dict[str, dict]:
        return {
            'username': dict(
                flags=['-u', '--username'],
                metavar='<user_id>',
                required=True
            ),
            'password': dict(
                flags=['-p', '--password'],
                metavar='<password>',
                required=True
            )
        }

    @override
    def handle(self, command_args: argparse.Namespace) -> dict:
        user_id, credentials = self._client.login(
            command_args.username, command_args.password
        )

        return {
            'id': str(user_id),
            **{
                name: str(value) for name, value in credentials.items()
            }
        }

    @override
    def get_completions(self, context: CompletionContext) -> Iterable[Completion]:
        if context.arg_descriptor.name == 'username':
            yield Completion(
                text='', display='<username>'
            )
        elif context.arg_descriptor.name == 'password':
            yield Completion(
                text='', display='<password>'
            )
        else:
            yield Completion(text='')


class ResourceHandlerFactory:
    MethodType: ClassVar = Literal['create', 'get', 'update', 'delete']
    HandlerMapType: ClassVar = Dict[
        str,
        Dict[MethodType, BaseResourceHandler]
    ]
    ParamValueFunction: ClassVar = Callable[[Self, str], Set]
    CreateHandlerSpec: ClassVar = TypedDict(
        'CreateHandlerSpec',
        {
            'query_type': Optional[QuerySelectionTypeDef],
            'request_type': Optional[RequestBodyTypeDef],
            'response_type': Optional[RequestBodyTypeDef],
            'parent': Optional[str],
            'param_value_provider': Optional[ParamValueFunction]
        }
    )
    _default_type_map: ClassVar = {
        'create': CreateResourceHandler,
        'get': QueryResourceHandler,
        'delete': DeleteResourceHandler
    }

    def __init__(self, client: AuthRestClient):
        self._client = client
        self._handlers: ResourceHandlerFactory.HandlerMapType = {}
        self.__add_builtin_handlers()

    @property
    def client(self) -> AuthRestClient:
        return self._client

    def handler(
            self,
            name: str,
            method: MethodType
    ) -> Optional[BaseResourceHandler]:
        return self._handlers[name][method]

    def create_handler[ResourceType](
            self,
            resource_name: str,
            resource_type: ResourceType,
            method_type: MethodType,
            **kwargs: Unpack['ResourceHandlerFactory.CreateHandlerSpec']
    ) -> BaseResourceHandler[ResourceType]:
        handler_type = ResourceHandlerFactory._default_type_map[method_type]
        if not (existing_resource := self._handlers.get(resource_name, None)):
            existing_resource = {}
            self._handlers[resource_name] = existing_resource
        elif existing_resource.get(method_type, None):
            raise ValueError(
                f"handler already exists:{method_type}@{dict(**kwargs)}"
            )

        resource_handler = handler_type(
            self._client,
            name=resource_name,
            resource_type=resource_type,
            query_type=kwargs.get('query_type', None),
            request_type=kwargs.get('request_type', None),
            response_type=kwargs.get('response_type', None),
            parent=(
                self.handler(parent_resource, 'get')
            ) if (parent_resource := kwargs.get('parent', None)) else None,
            arg_value_provider=(
                lambda arg: value_provider(self, arg)
            ) if (value_provider := kwargs.get('param_value_provider', None)) else None
        )
        self.__set_handler(method_type, resource_handler)

        return resource_handler

    def __add_builtin_handlers(self):
        login_handler = LoginHandler(self._client)
        self.__set_handler(
            'get', login_handler
        )

    def __set_handler(
            self,
            method_type: MethodType,
            handler: BaseResourceHandler
    ) -> BaseResourceHandler:
        resource_name = handler._name
        if not (existing_resource := self._handlers.get(resource_name, None)):
            existing_resource = {}
            self._handlers[resource_name] = existing_resource

        existing_resource[method_type] = handler
        return handler
