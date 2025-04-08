from datetime import datetime, timedelta
from typing import TypeVar, Generic, List, Optional, Self, Dict, Any, Annotated

from pydantic import (
    BaseModel, model_validator, Field, BeforeValidator, ConfigDict
)
from pydantic_core import to_jsonable_python

ModelTypeDef = TypeVar('ModelTypeDef', bound=BaseModel)


class BaseModelNoExtra(BaseModel):
    model_config = ConfigDict(extra='forbid', use_enum_values=True)


class DataSet[ModelTypeDef](BaseModel):
    data: List[ModelTypeDef] = []


class QueryDataPaginationToken(BaseModelNoExtra):
    query_id: str
    next_token: str

    @property
    def next_token_as_offset(self) -> int:
        return int(self.next_token)

    @next_token_as_offset.setter
    def next_token_as_offset(self, offset: int):
        self.next_token = str(offset)

    @classmethod
    def from_offset(cls, query_id: str, offset: int) -> Self:
        return QueryDataPaginationToken(
            query_id=query_id,
            next_token=str(offset)
        )


CustomQuerySelection = TypeVar('CustomQuerySelection', bound=BaseModel)


class QueryDataParams[CustomQuerySelection](BaseModelNoExtra):
    max_count: Optional[int] = None
    query: Optional[
        QueryDataPaginationToken | CustomQuerySelection
    ] = None

    @property
    def pagination_token(self) -> Optional[QueryDataPaginationToken]:
        return (
            self.query if self.has_pagination_token()
            else None
        )

    @property
    def query_selection(self) -> Optional[CustomQuerySelection]:
        return (
            self.query if self.has_query_selection()
            else None
        )

    def has_max_count(self) -> bool:
        return self.max_count is not None

    def has_pagination_token(self) -> bool:
        return self.query is not None and isinstance(self.query, QueryDataPaginationToken)

    def has_query_selection(self) -> bool:
        return self.query is not None and not self.has_pagination_token()

    @property
    def url_params_dict(self) -> Dict[str, Any]:
        params_dict = {}
        if self.has_max_count():
            params_dict[self.to_camelcase('max_count')] = self.max_count

        if self.query:
            params_dict.update(
                self.camelcase_keys(
                    to_jsonable_python(
                        self.query,
                        exclude_none=True,
                        by_alias=True
                    )
                )
            )

        return params_dict

    @classmethod
    def camelcase_keys(cls, object_dict: Dict[str, Any]) -> Dict[str, Any]:
        modified_dict = {}
        for key, value in object_dict.items():
            modified_dict[cls.to_camelcase(key)] = (
                cls.camelcase_keys(value) if isinstance(value, Dict) else value
            )

        return modified_dict

    @classmethod
    def to_camelcase(cls, value: str) -> str:
        modified = ""
        for part in value.split('_'):
            modified += part.capitalize()

        return modified


class QueryDataResult(DataSet):
    pagination_token: Optional[QueryDataPaginationToken] = None


RangeType = TypeVar('RangeType')


class Range[RangeType](BaseModelNoExtra):
    start: RangeType = Field(None)
    end: RangeType = Field(None)

    @model_validator(mode='after')
    def validate(self) -> Self:
        if self.start and self.end and (self.start > self.end):
            raise ValueError('Invalid negative range; start must be <= end')

        return self

    @property
    def length(self) -> timedelta:
        return self.end - self.start


class TimeRange(Range[datetime]):
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


class IntRange(Range[int]):
    start: Annotated[int, 2**63 - 1]
    end: Annotated[int, -(2**63)]


class UIntRange(Range[int]):
    start: Annotated[int, 2**64 - 1]
    end: Annotated[int, 0]


class FloatRange(Range[float]):
    start: Annotated[float, float('-inf')]
    end: Annotated[float, float('inf')]
