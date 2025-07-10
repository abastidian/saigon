import abc
import os
from contextlib import contextmanager
from typing import (
    TypeVar,
    Generic,
    Optional,
    NamedTuple,
    Any,
    Self,
    List,
    Callable,
    Protocol,
    Generator,
    runtime_checkable
)

from pydantic import BaseModel, field_serializer, ConfigDict

__all__ = [
    'NameValueItem',
    'Environment',
    'NodeEntityType',
    'NodeEntity',
    'EventHandler'
]


class NameValueItem[ValueType](NamedTuple):
    """Represents a simple name-value pair.

    Attributes:
        name (str): The name of the item.
        value (ValueType): The value associated with the name.
    """
    name: str
    value: ValueType


class Environment(abc.ABC, BaseModel):
    """Abstract base class for environment configurations.

    This class provides functionality to load environment variables into
    Pydantic models and set model attributes as environment variables.
    It allows for flexible handling of configuration based on both
    passed arguments and system environment variables.

    Attributes:
        model_config (ConfigDict): Pydantic configuration allowing extra fields.

    Example:
        Consider a configuration for a database::

            class DatabaseConfig(Environment):
                HOST: str
                PORT: int = 5432
                USER: str

            # If DB_HOST and DB_USER are set in environment variables
            # e.g., export DB_HOST="localhost", export DB_USER="admin"
            db_config = DatabaseConfig(PORT=5433)
            print(db_config.HOST) # Output: 'localhost'
            print(db_config.PORT) # Output: 5433
            print(db_config.USER) # Output: 'admin'

            # Set these values back to environment variables
            db_config.setvars()
            print(os.getenv('HOST')) # Output: 'localhost'
    """
    model_config = ConfigDict(extra='allow')

    def __init__(self, **kwargs):
        """Initializes the Environment instance.

        Loads attribute values from kwargs or environment variables if not provided.

        Args:
            **kwargs: Keyword arguments corresponding to the model's fields.
                Values provided here take precedence over environment variables.
        """
        super().__init__(**self.__load(**kwargs))

    def __load(self, **kwargs) -> dict:
        """Loads attribute values from keyword arguments or environment variables.

        Args:
            **kwargs: Keyword arguments to prioritize for loading.

        Returns:
            dict: A dictionary of loaded variables and their values.
        """
        return {
            var: value
            for var, _ in self.model_fields.items()
            if (value := kwargs.get(var, os.getenv(var)))
        }

    def setvars(self) -> Self:
        """Sets the instance's attribute values as environment variables.

        For each field defined in the model, if the instance has a value for that
        field, it will be converted to a string and set as an environment variable
        with the field's name.

        Returns:
            Self: The current instance, allowing for method chaining.
        """
        for var, _ in self.model_fields.items():
            if value := getattr(self, var):
                os.environ[var] = str(value)

        return self.__class__()


NodeEntityType = TypeVar('NodeEntityType', bound=BaseModel)


class NodeEntity(BaseModel, Generic[NodeEntityType]):
    """Represents a node in a tree-like structure, holding an entity.

    This class allows for building hierarchical data structures where each node
    contains a Pydantic model (`entity`), and can have a parent and multiple children.

    Attributes:
        entity (NodeEntityType): The Pydantic model payload for this node.
        parent (Optional[Self]): The parent node in the hierarchy. Defaults to None.
        children (List[Self]): A list of child nodes. Defaults to an empty list.

    Example::

        class Document(BaseModel):
            id: str
            name: str

        root_doc = Document(id="1", name="Root Document")
        child_doc_1 = Document(id="2", name="Child Document 1")
        child_doc_2 = Document(id="3", name="Child Document 2")

        root_node = NodeEntity(entity=root_doc)
        child_node_1 = NodeEntity(entity=child_doc_1)
        child_node_2 = NodeEntity(entity=child_doc_2)

        root_node.add_child(child_node_1)
        root_node.add_child(child_node_2)

        print(child_node_1.parent.entity.name) # Output: Root Document

        # Traverse and print node names
        def print_node_name(node: NodeEntity):
            print(f"Node: {node.entity.name}")

        root_node.traverse(print_node_name)
        # Expected Output:
        # Node: Root Document
        # Node: Child Document 1
        # Node: Child Document 2
    """
    entity: NodeEntityType
    parent: Optional[Self] = None
    children: List[Self] = []

    def add_child(self, node: Self):
        """Adds a child node to the current node.

        Also sets the `parent` attribute of the added child node to this node.

        Args:
            node (Self): The node to add as a child.
        """
        self.children.append(node)
        node.parent = self

    def traverse(
        self, visitor: Callable[[Self], Any]
    ):
        """Performs a depth-first traversal of the node and its children.

        Applies a visitor function to the current node and then recursively
        to all its children.

        Args:
            visitor (Callable[[Self], Any]): A callable that takes a NodeEntity
                instance as input.
        """
        visitor(self)
        for child in self.children:
            child.traverse(visitor)

    @field_serializer('parent')
    def serialize_parent(self, parent: NodeEntityType, _info) -> Optional[str]:
        """Serializes the 'parent' field to its 'name' attribute if it exists.

        This custom serializer is used by Pydantic when serializing a NodeEntity
        instance. It prevents recursive serialization of the parent object and
        instead just includes its name.

        Args:
            parent (NodeEntityType): The parent entity being serialized.
            _info: Pydantic's SerializationInfo object (unused here but required).

        Returns:
            Optional[str]: The name of the parent entity if it has a 'name' attribute,
                otherwise None.
        """
        return getattr(parent, 'name') if hasattr(parent, 'name') else None


@runtime_checkable
class EventHandler[InputData, OutputData](Protocol):
    """Defines a protocol for event handlers.

    An `EventHandler` is designed to process input data within a context,
    yielding an output. This is typically used for operations that involve
    resource setup before processing and cleanup afterwards. Additionally, a
    protocol convention is helpful to create high-order functions and classes
    in order to reuse functionality.

    Type variables:
        InputData: The type of data expected as input to the event.
        OutputData: The type of data yielded as output from the event.

    Example::

        class FileProcessor(EventHandler[str, bytes]):
            @contextmanager
            def on_event(self, filepath: str) -> Generator[bytes, Any, Any]:
                print(f"Opening file: {filepath}")
                file_content = b""
                try:
                    with open(filepath, 'rb') as f:
                        file_content = f.read()
                    yield file_content
                finally:
                    print(f"Closing file: {filepath}")

        # Usage
        processor = FileProcessor()
        with processor.on_event("my_document.txt") as content:
            print(f"Processing content (first 10 bytes): {content[:10]}")
        # Expected output:
        # Opening file: my_document.txt
        # Processing content (first 10 bytes): b'...'
        # Closing file: my_document.txt
    """
    @abc.abstractmethod
    @contextmanager
    def on_event(self, input_data: InputData) -> Generator[OutputData]:
        """
        An abstract context manager method for handling events.

        This method defines the core logic for an event handler,
        providing a context for processing input data and yielding output data.

        Args:
            input_data: The input data to be processed by the event handler.

        Yields:
            OutputData: The output data generated by the event handler.
        """
        ...
