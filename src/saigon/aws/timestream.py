import abc
from datetime import datetime, timezone
from typing import (
    List,
    Generic,
    Tuple,
    Self,
    Optional,
    Type,
    Dict,
    override,
    Callable,
    ClassVar,
    Any
)
import logging
import base64

import boto3
from mypy_boto3_timestream_write.client import TimestreamWriteClient
from mypy_boto3_timestream_write.type_defs import WriteRecordsRequestRequestTypeDef
from mypy_boto3_timestream_query.client import TimestreamQueryClient
from mypy_boto3_timestream_query.type_defs import (
    QueryRequestRequestTypeDef,
    QueryResponseTypeDef,
)
from mypy_boto3_timestream_query.type_defs import (
    ColumnInfoTypeDef,
    RowTypeDef,
    DatumTypeDef,
)
from mypy_boto3_timestream_write.type_defs import (
    RecordTypeDef,
    MeasureValueTypeDef as WriteMeasureValueTypeDef,
    DimensionTypeDef
)
from mypy_boto3_timestream_write.literals import (
    MeasureValueTypeType as WriteValueType
)
from mypy_boto3_timestream_query.literals import (
    ScalarTypeType
)

from pydantic import FiniteFloat
from pydantic.fields import FieldInfo

from saigon.model import (
    ModelTypeDef,
    DataSet,
    QueryDataParams,
    QueryDataPaginationToken,
    QueryDataResult
)
from saigon.utils import NameValueItem

__all__ = [
    'RecordRowIt',
    'RecordConverter',
    'MultiMeasureConverter',
    'SingleMeasureConverter',
    'MetricValueType',
    'TimestreamClientBase',
    'PartitionKeySpec'
]

MetricValueType = int | FiniteFloat | str
PartitionKeySpec = NameValueItem

TIMESTREAM_MEASURE_COLUMN_NAME = 'measure_name'

logger = logging.getLogger(__name__)


class RecordRowIt:
    def __init__(
            self,
            record_columns: List[ColumnInfoTypeDef],
            record_row: RowTypeDef,
            start_index=0,
            copy_record=False
    ):
        self._record_columns = record_columns.copy() if copy_record else record_columns
        self._record_row = record_row.copy() if copy_record else record_row
        self._index = start_index

    def get(self) -> Tuple[ColumnInfoTypeDef, DatumTypeDef]:
        return (
            self._record_columns[self._index],
            self._record_row['Data'][self._index]
        )

    def pop(self) -> Tuple[ColumnInfoTypeDef, DatumTypeDef]:
        row_item = (
            self._record_columns.pop(self._index),
            self._record_row['Data'].pop(self._index)
        )
        return row_item

    def increment(self) -> Self:
        self._index += 1
        return self

    def has_next(self) -> bool:
        return self._index < len(self._record_columns)

    def finish(self) -> Self:
        self._index = len(self._record_columns)
        return self

    def copy(self, copy_record=False) -> Self:
        return self.__class__(
            self._record_columns, self._record_row, self._index, copy_record
        )

    def reset(self) -> Self:
        self._index = 0
        return self


class RecordConverter(abc.ABC, Generic[ModelTypeDef]):
    MEASURE_TYPE_NAME: ClassVar[Dict[Type, WriteValueType]] = {
        int: 'BIGINT',
        str: 'VARCHAR',
        float: 'DOUBLE',
        bool: 'BOOLEAN',

    }
    COLUMN_TYPES: ClassVar[Dict[ScalarTypeType, Callable[[str], Any]]] = {
        'BIGINT': int,
        'INTEGER': int,
        'DOUBLE': float,
        'TIMESTAMP': lambda value: datetime.fromisoformat(value).replace(tzinfo=timezone.utc),
        'TIME': lambda value: datetime.fromisoformat(value).replace(tzinfo=timezone.utc),
        'DATE': lambda value: datetime.fromisoformat(value).replace(tzinfo=timezone.utc),
        'VARCHAR': str,
        'BOOLEAN': bool
    }

    def __init__(self, model_type: Type[ModelTypeDef]):
        self._model_type = model_type

    @property
    def model_type(self) -> Type[ModelTypeDef]:
        return self._model_type

    @abc.abstractmethod
    def from_record(
            self,
            record_columns: List[ColumnInfoTypeDef],
            record_row: RowTypeDef,
            **kwargs
    ) -> ModelTypeDef:
        raise NotImplementedError

    @abc.abstractmethod
    def to_record(
            self,
            data: ModelTypeDef,
            include_partition_key=True,
            **kwargs
    ) -> RecordTypeDef:
        raise NotImplementedError

    @classmethod
    def _parse_value(
            cls, column: ColumnInfoTypeDef, row_item: DatumTypeDef
    ) -> MetricValueType | None:
        item_value = row_item.get('ScalarValue', None)
        return cls.COLUMN_TYPES[column['Type']['ScalarType']](
            item_value
        ) if item_value else None

    @classmethod
    def _convert_item(
            cls, column: ColumnInfoTypeDef, row_item: DatumTypeDef
    ) -> dict:
        value = cls._parse_value(column, row_item)
        return {
            column['Name']: value
        } if value else {}

    @classmethod
    def _to_dimensions(
            cls,
            data: ModelTypeDef,
            partition_key: Optional[str] = None,
            include_partition_key=True,
            extra_dimensions: Optional[List[str]] = None
    ) -> List[DimensionTypeDef]:
        included_dimensions = (
            extra_dimensions if extra_dimensions else [] +
            ([partition_key] if include_partition_key and partition_key else [])
        )

        return [
            {
                'Name': dim_name,
                'Value': str(getattr(data, dim_name))
            }
            for dim_name in included_dimensions
        ]

    @classmethod
    def _to_record_overrides(cls, **kwargs) -> Dict[str, str]:
        write_record_params = {}
        for param, value_override in kwargs.items():
            if param in RecordTypeDef.__annotations__:
                write_record_params[param] = value_override

        return write_record_params

    @classmethod
    def _to_measure_value(cls, data: ModelTypeDef, field_name: str) -> str | None:
        field_value = getattr(data, field_name)
        return str(field_value) if field_value else None


class MultiMeasureConverter(RecordConverter[ModelTypeDef]):
    DEFAULT_METRIC_FIELD: ClassVar[str] = 'metrics'

    def __init__(
            self,
            model_type: Type[ModelTypeDef],
            metric_name_field: Optional[str] = None,
            partition_key: Optional[str] = None,
            extra_dimensions: Optional[List[str]] = None,
            flat_conversion: Optional[bool] = False
    ):
        super().__init__(model_type)
        self._partition_key = partition_key
        self._extra_dimensions = extra_dimensions if extra_dimensions else []
        self._metric_name_field = metric_name_field
        self._known_fields = model_type.__fields__
        self._flat_conversion = flat_conversion

    @override
    def from_record(
            self,
            record_columns: List[ColumnInfoTypeDef],
            record_row: RowTypeDef,
            **kwargs
    ) -> ModelTypeDef:
        row_it = RecordRowIt(
            record_columns, record_row
        )
        converted = {}
        metric_name_field = self._metric_name_field
        # Iterate over all columns and convert each
        while row_it.has_next():
            column, row_item = row_it.get()
            column_name = column['Name']
            if column_name in self._known_fields:
                converted.update(
                    super()._convert_item(column, row_item)
                )
            elif column_name == TIMESTREAM_MEASURE_COLUMN_NAME:
                measure_name = super()._parse_value(column, row_item)
                if metric_name_field is None:
                    metric_name_field = measure_name
                if metric_name_field not in self._known_fields:
                    raise ValueError(f"Unexpected column measure name={measure_name}")

                if self._flat_conversion:
                    converted[metric_name_field] = measure_name
                else:
                    # Currently multi-measure are extracted as dict of name-value pairs
                    metric_value = dict()
                    converted[metric_name_field] = metric_value
            else:
                if not metric_name_field:
                    raise ValueError('Missing measure name column')
                if self._flat_conversion:
                    converted.update(
                        super()._convert_item(column, row_item)
                    )
                else:
                    # Unknown columns are considered individual metrics
                    # For multi-measure, these metrics map into the appropriate
                    # metric dict field
                    converted[metric_name_field].update(
                        super()._convert_item(column, row_item)
                    )

            row_it.increment()

        return self.model_type(**converted)

    @override
    def to_record(
            self,
            data: ModelTypeDef,
            include_partition_key: bool = True,
            **kwargs
    ) -> RecordTypeDef:
        metric_field = (
            self._metric_name_field if self._metric_name_field
            else self.DEFAULT_METRIC_FIELD
        )

        # Add non-metrics (and also metrics if flat_conversion)
        measure_values = []
        for field_name in self._known_fields:
            if (
                    field_name not in
                    [metric_field, 'time', self._partition_key] + self._extra_dimensions
            ):
                if field_value := getattr(data, field_name):
                    measure_values.append(
                        {
                            'Name': field_name,
                            'Value': str(field_value),
                            'Type': self._get_column_type(field_value)
                        }
                    )
        if not self._flat_conversion:
            # Add metric values in its own metric field (as dict) unless is the flat conversion
            # in which case individual metrics are already converted in the non-metrics section
            measure_values += self._metrics_to_measures(data, metric_field)

        return dict(
            {
                'Dimensions': super()._to_dimensions(
                    data, self._partition_key, include_partition_key, self._extra_dimensions
                ),
                'Time': str(int(getattr(data, 'time').timestamp() * 1000)),
                'TimeUnit': 'MILLISECONDS',
                'MeasureValueType': 'MULTI',
                'MeasureName': (
                    getattr(data, metric_field) if self._flat_conversion else metric_field
                ),
                'MeasureValues': measure_values
            },
            **super()._to_record_overrides(**kwargs)
        )

    @classmethod
    def _get_write_measure_type(
            cls, model_fields: Dict[str, FieldInfo], field_name: str
    ) -> WriteValueType:
        return cls._get_column_type(model_fields[field_name].annotation)

    @classmethod
    def _metrics_to_measures(
            cls, data: ModelTypeDef, metric_field: str
    ) -> List[WriteMeasureValueTypeDef]:
        return [
            {
                'Name': metric_name,
                'Value': str(metric_value),
                'Type': cls._get_column_type(metric_value),
            } for metric_name, metric_value in getattr(data, metric_field).items()
        ]

    @classmethod
    def _get_column_type(cls, value_or_type: Any | Type[Any]) -> WriteValueType:
        matching_type = cls.MEASURE_TYPE_NAME.get(
            value_or_type if isinstance(value_or_type, type) else type(value_or_type),
            None
        )
        return (
            matching_type if matching_type
            else cls.MEASURE_TYPE_NAME[str]
        )


class SingleMeasureConverter(RecordConverter[ModelTypeDef]):
    DEFAULT_METRIC_NAME_FIELD: ClassVar[str] = 'name'
    DEFAULT_METRIC_VALUE_FIELD: ClassVar[str] = 'value'

    def __init__(
            self,
            model_type: Type[ModelTypeDef],
            metric_name_field: Optional[str] = None,
            metric_value_field: Optional[str] = None,
            partition_key: Optional[str] = None,
            extra_dimensions: Optional[List[str]] = None
    ):
        super().__init__(model_type)
        self._metric_name_field = metric_name_field
        self._metric_value_field = metric_value_field
        self._extra_dimensions = extra_dimensions if extra_dimensions else []
        self._partition_key = partition_key
        self._known_fields = model_type.__fields__

    @override
    def from_record(
            self,
            record_columns: List[ColumnInfoTypeDef],
            record_row: RowTypeDef,
            **kwargs
    ) -> ModelTypeDef:
        row_it = RecordRowIt(
            record_columns, record_row
        )
        converted = {}
        metric_name_field = self._metric_name_field
        measure_name = None
        while row_it.has_next():
            column, row_item = row_it.get()
            column_name = column['Name']
            if column_name == TIMESTREAM_MEASURE_COLUMN_NAME:
                measure_name = RecordConverter._parse_value(
                    column, row_item
                )
                if metric_name_field:
                    converted[metric_name_field] = measure_name
                else:
                    metric_name_field = measure_name
            else:
                if column_name in self._known_fields:
                    converted.update(
                        super()._convert_item(column, row_item)
                    )
                else:
                    if not measure_name or not column_name.startswith(measure_name):
                        raise ValueError('Unknown column={column_name}')

                    # Next non-null column is the actual metric value
                    metric_value_field = (
                        self._metric_value_field if self._metric_value_field else metric_name_field
                    )
                    if not metric_value_field:
                        raise ValueError('Missing metric value field')

                    converted[metric_value_field] = RecordConverter._parse_value(
                        column, row_item
                    )

            row_it.increment()

        return self._model_type(**converted)

    @override
    def to_record(
            self,
            data: ModelTypeDef,
            include_partition_key: bool = True,
            **kwargs
    ) -> RecordTypeDef:
        if self._metric_value_field:
            measure_name = (
                getattr(data, self._metric_name_field) if self._metric_name_field
                else self._metric_value_field
            )
            measure_value = getattr(data, self._metric_value_field)
        else:
            metric_name_field = (
                self._metric_name_field if self._metric_name_field
                else self.DEFAULT_METRIC_NAME_FIELD
            )
            measure_name = getattr(data, metric_name_field)
            measure_value = getattr(data, self.DEFAULT_METRIC_VALUE_FIELD)

        return dict(
            {
                'Dimensions': super()._to_dimensions(
                    data, self._partition_key, include_partition_key, self._extra_dimensions
                ),
                'Time': str(int(getattr(data, 'time').timestamp() * 1000)),
                'TimeUnit': 'MILLISECONDS',
                'MeasureName': measure_name,
                'MeasureValueType': super().MEASURE_TYPE_NAME[type(measure_value)],
                'MeasureValue': str(measure_value)
            },
            **super()._to_record_overrides(**kwargs)
        )


class TimestreamClientBase(abc.ABC):
    def __init__(
            self,
            database_name: str,
            converters: List[RecordConverter],
            table_names_map: Dict[Type[ModelTypeDef], str]
    ):
        self.__database_name = database_name
        self.write_client: TimestreamWriteClient = boto3.client('timestream-write')
        self.query_client: TimestreamQueryClient = boto3.client('timestream-query')
        self._data_type_info: Dict[
            Type[ModelTypeDef],
            Tuple[str, RecordConverter[ModelTypeDef]]
        ] = {
            converter.model_type: (
                table_names_map[converter.model_type], converter
            ) for converter in converters
        }

    @abc.abstractmethod
    def get_read_query(
            self,
            model_type: Type[ModelTypeDef],
            query_params: QueryDataParams,
            partition_key: Optional[PartitionKeySpec] = None,
    ) -> str:
        raise NotImplementedError

    @property
    def database_name(self) -> str:
        return self.__database_name

    def write_data(
            self,
            data_type: Type[ModelTypeDef],
            data_set: DataSet[ModelTypeDef],
            partition_key: Optional[PartitionKeySpec] = None,
            **kwargs
    ):
        write_params = self.__get_write_records_param(
            data_type, data_set, partition_key, **kwargs
        )
        logger.info('Write frames to timestream')
        logger.debug(f"write params={write_params}")
        self.write_client.write_records(**write_params)

    def read_data(
            self,
            model_type: Type[ModelTypeDef],
            query_params: QueryDataParams,
            partition_key: Optional[PartitionKeySpec] = None,
            **kwargs
    ) -> QueryDataResult[ModelTypeDef]:
        # build query operation arguments
        if isinstance(query_params.query, QueryDataPaginationToken):
            read_params: QueryRequestRequestTypeDef = {
                'QueryString': base64.b64decode(
                    query_params.query.query_id.encode()
                ).decode(),
                'NextToken': query_params.query.next_token
            }
        else:
            read_params = {
                'QueryString': self.get_read_query(
                    model_type,
                    query_params,
                    partition_key
                )
            }

        if query_params.max_count:
            read_params['MaxRows'] = query_params.max_count

        # Run query
        query_response = self.query_client.query(**read_params)
        if query_response.get('NextToken', None) and not query_response['Rows']:
            # first query invocation with pagination. Read again with the returned token
            # to retrieve the first batch of rows
            query_response = self.query_client.query(
                **read_params,
                NextToken=query_response['NextToken']
            )

        # Return deserialized data set and, if present, the pagination token
        data_set = self.__deserialize_response(
            model_type, query_response
        )
        next_token = query_response.get('NextToken', None)
        pagination_token = QueryDataPaginationToken(
            query_id=base64.b64encode(read_params['QueryString'].encode()).decode(),
            next_token=query_response['NextToken']
        ) if next_token else None

        return QueryDataResult(
            data=data_set.data,
            pagination_token=pagination_token
        )

    def __get_write_records_param(
            self,
            data_type: Type[ModelTypeDef],
            data_set: DataSet[ModelTypeDef],
            partition_key: Optional[PartitionKeySpec] = None,
            **kwargs
    ) -> WriteRecordsRequestRequestTypeDef:
        table_name, converter = self._data_type_info[data_type]
        return {
            'DatabaseName': self.__database_name,
            'TableName': table_name,
            'CommonAttributes': dict(
                {
                    'Dimensions': [
                        {'Name': partition_key.name, 'Value': partition_key.value},
                    ],
                } if partition_key else {},
            ),
            'Records': [
                converter.to_record(
                    frame,
                    include_partition_key=(partition_key is None),
                    **kwargs
                )
                for frame in data_set.data
            ]
        }

    def __deserialize_response(
            self,
            model_type: Type[ModelTypeDef],
            response: QueryResponseTypeDef
    ) -> DataSet[ModelTypeDef]:
        data_list: List[model_type] = []
        column_info = response['ColumnInfo']
        _, converter = self._data_type_info[model_type]
        for row in response['Rows']:
            converted = converter.from_record(
                column_info, row
            )
            data_list.append(converted)

        return DataSet[model_type](
            data=data_list
        )
