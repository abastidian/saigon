import base64
import json
from datetime import datetime, timedelta
from typing import TypeVar, List, Optional, Self, Dict, Any, Annotated, Type, override

from pydantic import (
    BaseModel, model_validator, Field, BeforeValidator, ConfigDict
)
from pydantic_core import to_jsonable_python

__all__ = [
    'BaseModelNoExtra',
    'DataSet',
    'QueryDataPaginationToken',
    'QueryDataParams',
    'QueryDataResult',
    'Range',
    'TimeRange',
    'EmptyContent',
    'ModelTypeDef',
]

ModelTypeDef = TypeVar('ModelTypeDef', bound=BaseModel)


class BaseModelNoExtra(BaseModel):
    """
    BaseModel with extra fields forbidden by default.

    This configuration ensures that any input data containing fields
    not explicitly defined in the model will raise a validation error.
    It also sets `use_enum_values` to True for convenience.
    """
    model_config = ConfigDict(extra='forbid', use_enum_values=True)


class DataSet[ModelType: BaseModel](BaseModel):
    """
    A generic data set model containing a list of items of a specified ModelType.

    Attributes:
        data (List[ModelType]): A list of data items. Defaults to an empty list.
    """
    data: List[ModelType] = []


class QueryDataPaginationToken(BaseModelNoExtra):
    """
    Represents a pagination token for querying data, typically used for cursor-based pagination.

    Attributes:
        query_id (str): An identifier for the specific query. It must allow to retrieve the
            originating paginated query (e.g, an encoded set of params).
        next_token (str | int): The token indicating the starting point for the next page of results.
            This is typically an offset integer.
    """

    query_id: str
    next_token: str | int

    @property
    def offset(self) -> int:
        """
        Converts the `next_token` to an integer offset.

        Returns:
            int: The `next_token` as an integer offset.
        """
        return int(self.next_token)

    @classmethod
    def from_offset(cls, query_id: str, offset: int) -> Self:
        """
        Creates a QueryDataPaginationToken instance from a query ID and an integer offset.

        Args:
            query_id (str): An identifier for the specific query.
            offset (int): The integer offset to use as the next token.

        Returns:
            Self: A new QueryDataPaginationToken instance.
        """
        return QueryDataPaginationToken(
            query_id=query_id,
            next_token=offset
        )


class QueryDataParams[QuerySelection: BaseModel](BaseModelNoExtra):
    """
    Parameters for querying data, supporting max count and either
    a pagination token or a query selection model.

    Attributes:
        max_count (Optional[int]): The maximum number of results to return. Defaults to None.
        query (Optional[QueryDataPaginationToken | QuerySelection]): Either a pagination token
            or a detailed query selection model. Defaults to None.
    """
    max_count: Optional[int] = None
    query: Optional[
        QueryDataPaginationToken | QuerySelection
    ] = None

    @property
    def pagination_token(self) -> Optional[QueryDataPaginationToken]:
        """
        Returns the query as a QueryDataPaginationToken if it contains a pagination token,
        otherwise returns None.

        Returns:
            Optional[QueryDataPaginationToken]: The pagination token if present, otherwise None.
        """
        return (
            self.query if self.has_pagination_token()
            else None
        )

    @property
    def query_selection(self) -> Optional[QuerySelection]:
        """
        Returns the query as a QuerySelection model if it represents a query selection,
        otherwise returns None.

        Returns:
            Optional[QuerySelection]: The query selection model if present, otherwise None.
        """
        return (
            self.query if self.has_query_selection()
            else None
        )

    def has_max_count(self) -> bool:
        """
        Checks if a maximum count is specified in the query parameters.

        Returns:
            bool: True if `max_count` is not None, False otherwise.
        """
        return self.max_count is not None

    def has_pagination_token(self) -> bool:
        """
        Checks if the query member represents a pagination token.

        Returns:
            bool: True if `query` is a QueryDataPaginationToken instance, False otherwise.
        """
        return self.query is not None and isinstance(self.query, QueryDataPaginationToken)

    def has_query_selection(self) -> bool:
        """
        Checks if the query parameter represents a query selection model (and not a pagination token).

        Returns:
            bool: True if `query` is present and not a pagination token, False otherwise.
        """
        return self.query is not None and not self.has_pagination_token()

    def encode_query_selection(self) -> str:
        """
        Encodes the `query_selection` into a URL-safe base64 string.

        This method is typically used to convert a complex query selection
        into a string that can be used as a `query_id` in a pagination token.

        Returns:
            str: The URL-safe base64 encoded string of the query selection.
        """
        return base64.urlsafe_b64encode(
            json.dumps(
                to_jsonable_python(self.query_selection)
            ).encode()
        ).decode()

    def decode_query_selection(
            self, selection_type: Type[QuerySelection]
    ) -> QuerySelection:
        """
        Decodes the `query_id` from this object's pagination token back into a
        QuerySelection model.

        This method assumes that the `query_id` of the pagination token
        contains a base64 encoded JSON string of the original query selection.

        Args:
            selection_type (Type[QuerySelection]): The Pydantic model type to which the decoded
                selection should be cast.

        Returns:
            QuerySelection: The decoded QuerySelection model.
        """
        query_selection_dict = json.loads(
            base64.b64decode(self.pagination_token.query_id.encode()).decode()
        )
        return selection_type(**query_selection_dict)

    @property
    def url_params_dict(self, camel_case=True) -> Dict[str, Any]:
        """
        Generates a dictionary of URL parameters from the query data parameters.
        Keys can optionally be converted to CamelCase.

        Args:
            camel_case (bool): Whether parameter names are formatted as CamelCase.

        Returns:
            Dict[str, Any]: A dictionary suitable for URL query parameters.
        """

        params_dict = {}
        if self.has_max_count():
            max_count_key = 'max_count'
            params_dict[
                self.to_camelcase(max_count_key)
                if camel_case else max_count_key
            ] = self.max_count

        if self.query:
            params_dict.update(
                to_jsonable_python(
                    self.query,
                    exclude_none=True,
                    by_alias=True
                )
            )
            if camel_case:
                params_dict.update(
                    self.camelcase_keys(params_dict)
                )

        return params_dict

    @classmethod
    def camelcase_keys(cls, object_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively converts all string keys in a dictionary to camelCase.

        Args:
            object_dict (Dict[str, Any]): The dictionary whose keys are to be converted.

        Returns:
            Dict[str, Any]: A new dictionary with keys converted to camelCase.
        """
        modified_dict = {}
        for key, value in object_dict.items():
            modified_dict[cls.to_camelcase(key)] = (
                cls.camelcase_keys(value) if isinstance(value, Dict) else value
            )

        return modified_dict

    @classmethod
    def to_camelcase(cls, value: str) -> str:
        """
        Converts a snake_case string to upper camelCase.

        Args:
            value (str): The snake_case string to convert.

        Returns:
            str: The camelCase string.
        """
        modified = ""
        for part in value.split('_'):
            modified += part.capitalize()

        return modified


class QueryDataResult(DataSet):
    """
    Represents the result of a data query, including the data set
    and an optional pagination token for subsequent queries.

    Attributes:
        pagination_token (Optional[QueryDataPaginationToken]): An optional pagination token
            for fetching the next page of results.
    """
    pagination_token: Optional[QueryDataPaginationToken] = None


class Range[RangeType: object](BaseModelNoExtra):
    """
    A generic range model with a start and an end value.
    It ensures that the start value is not greater than the end value.

    Attributes:
        start (RangeType): The starting value of the range. Defaults to None.
        end (RangeType): The ending value of the range. Defaults to None.
    """
    model_config = ConfigDict(validate_by_name=True)

    start: RangeType = Field(None)
    end: RangeType = Field(None)

    @model_validator(mode='after')
    def validate(self) -> Self:
        """
        Pydantic model validator to ensure that the start value is not greater than the end value.

        Raises:
            ValueError: If `start` is greater than `end`.

        Returns:
            Self: The validated Range instance.
        """
        if self.start and self.end and (self.start > self.end):
            raise ValueError('Invalid negative range; start must be <= end')

        return self

    @property
    def length[Delta](self) -> Delta:
        """
        Returns the length of the range.

        This property is expected to be used with types that support subtraction,
        like `datetime` or `timedelta`.

        Returns:
            Delta: The difference between the end and start values.
        """
        return self.end - self.start


class TimeRange(Range[datetime]):
    """
    A specific Range implementation for `datetime` objects, representing a time interval.

    Attributes:
        start (datetime): The start time of the range. Defaults to datetime(1, 1, 1, 0, 0, 0).
            Serialized as 'start_time'.
        end (datetime): The end time of the range. Defaults to the current datetime if not provided.
            Serialized as 'end_time'.
    """
    start: Annotated[
        datetime,
        Field(
            datetime(
                year=1, month=1, day=1, hour=0, minute=0, microsecond=0
            ),
            serialization_alias='start_time'
        )
    ]
    end: Annotated[
        datetime,
        Field(None, serialization_alias='end_time'),
        BeforeValidator(lambda x: x if x else datetime.now())
    ]

    @override
    def length(self) -> timedelta:
        """
        Returns the length of the TimeRange as a timedelta.

        Overrides:
            Range.length: Provides a concrete return type for timedelta.

        Returns:
            timedelta: The duration between the end and start datetimes.
        """
        return super().length


class IntRange(Range[int]):
    """
    A specific Range implementation for `int` values, with default min/max values
    representing the full range of a 64-bit signed integer.

    Attributes:
        start (int): The start integer of the range. Defaults to 2^63 - 1.
        end (int): The end integer of the range. Defaults to -(2^63).
    """
    start: Annotated[int, 2**63 - 1]
    end: Annotated[int, -(2**63)]


class UIntRange(Range[int]):
    """
    A specific Range implementation for unsigned `int` values, with default min/max values
    representing the full range of a 64-bit unsigned integer.

    Attributes:
        start (int): The start integer of the range. Defaults to 2^64 - 1.
        end (int): The end integer of the range. Defaults to 0.
    """
    start: Annotated[int, 2**64 - 1]
    end: Annotated[int, 0]


class FloatRange(Range[float]):
    """
    A specific Range implementation for `float` values, with default min/max values
    representing negative and positive infinity.

    Attributes:
        start (float): The start float of the range. Defaults to negative infinity.
        end (float): The end float of the range. Defaults to positive infinity.
    """
    start: Annotated[float, float('-inf')]
    end: Annotated[float, float('inf')]


class EmptyContent(BaseModel):
    """
    A Pydantic model designed to handle empty or null content gracefully.
    It transforms `None` input into an empty dictionary.
    """
    @model_validator(mode='before')
    @classmethod
    def _check_for_null(cls, data: Any) -> Any:
        """
        Pydantic model validator that runs before parsing.

        If the input `data` is `None`, it returns an empty dictionary `{}`.
        Otherwise, it returns the data as is.

        Args:
            data (Any): The input data received by the model.

        Returns:
            Any: An empty dictionary if data is None, otherwise the original data.
        """
        if data is None:
            return {}

        return data