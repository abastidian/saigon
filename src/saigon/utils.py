from typing import (
    TypeVar, Generic, Optional, NamedTuple, Any, Self, List, Callable, ClassVar
)
import abc
import os

from pydantic import BaseModel, field_serializer, ConfigDict, model_validator


class NameValueItem(NamedTuple):
    name: str
    value: Any


class Environment(abc.ABC, BaseModel):
    model_config = ConfigDict(extra='allow')

    def __init__(self, **kwargs):
        super().__init__(**self.__load(**kwargs))

    def __load(self, **kwargs) -> dict:
        return {
            var: value
            for var, _ in self.model_fields.items()
            if (value := kwargs.get(var, os.getenv(var)))
        }

    def setvars(self) -> Self:
        for var, _ in self.model_fields.items():
            if value := getattr(self, var):
                os.environ[var] = str(value)

        return self.__class__()


NodeEntityType = TypeVar('NodeEntityType', bound=BaseModel)


class NodeEntity(BaseModel, Generic[NodeEntityType]):
    entity: NodeEntityType
    parent: Optional[Self] = None
    children: List[Self] = []

    def add_child(self, node: Self):
        self.children.append(node)
        node.parent = self

    def traverse(
        self, visitor: Callable[[Self], Any]
    ):
        visitor(self)
        for child in self.children:
            child.traverse(visitor)

    @field_serializer('parent')
    def serialize_parent(self, parent: NodeEntityType, _info) -> Optional[str]:
        return getattr(parent, 'name') if hasattr(parent, 'name') else None
