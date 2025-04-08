from typing import Tuple, List, Dict, Type
from datetime import datetime, timezone

from mypy_boto3_timestream_query.type_defs import (
    ColumnInfoTypeDef, RowTypeDef
)
from mypy_boto3_timestream_query.literals import ScalarTypeType
from mypy_boto3_timestream_write.type_defs import (
    RecordTypeDef
)

from pydantic import BaseModel

from saigon.aws.timestream import MetricValueType, RecordConverter


QUERY_MEASURE_TYPE_NAME: Dict[Type, ScalarTypeType] = {
        int: 'BIGINT',
        str: 'VARCHAR',
        float: 'DOUBLE',
        bool: 'BOOLEAN',
        datetime: 'TIMESTAMP'
    }


class RecordMultiMeasureSample(BaseModel):
    time: datetime
    string_value: str
    id: int
    metrics: Dict[str, MetricValueType]


class RecordSingleMeasureSampleGeneric(BaseModel):
    id: int
    time: datetime
    name: str
    value: MetricValueType


class RecordSingleMeasureSampleCustom(BaseModel):
    id: int
    time: datetime
    my_metric: MetricValueType


def make_multi_measure_sample(**kwargs) -> RecordMultiMeasureSample:
    default_columns = dict(
        time=datetime.fromisoformat('2024-09-30 20:23:40.000000000').replace(tzinfo=timezone.utc),
        string_value='test string',
        id=1,
        metrics=dict(
            input_pressure=1.0,
            output_pressure=0.5)
    )
    return RecordMultiMeasureSample(
        **dict(default_columns, **kwargs)
    )


def make_single_measure_sample_generic(**kwargs) -> RecordSingleMeasureSampleGeneric:
    default_columns = dict(
        id=1,
        time=datetime.fromisoformat('2024-09-30 20:23:40.000000000').replace(tzinfo=timezone.utc),
        name='my_metric',
        value=0.5
    )
    return RecordSingleMeasureSampleGeneric(
        **dict(default_columns, **kwargs)
    )


def make_single_measure_sample_custom(**kwargs) -> RecordSingleMeasureSampleCustom:
    default_columns = dict(
        id=1,
        time=datetime.fromisoformat('2024-09-30 20:23:40.000000000').replace(tzinfo=timezone.utc),
        my_metric=0.5
    )
    return RecordSingleMeasureSampleCustom(
        **dict(default_columns, **kwargs)
    )


def make_record_row(**kwargs) -> Tuple[List[ColumnInfoTypeDef], RowTypeDef]:
    return (
        [
            {'Name': name, 'Type': {'ScalarType': QUERY_MEASURE_TYPE_NAME[type(value)]}}
            for name, value in kwargs.items()
        ],
        {
            'Data': [
                {'ScalarValue': str(value)} for _, value in kwargs.items()
            ]
        }
    )


def make_record_multi_measure_row(**kwargs):
    default_columns = dict(
        time=datetime.fromisoformat('2024-09-30 20:23:40.000000000'),
        string_value='test string',
        measure_name='metrics',
        id=1,
        input_pressure=1.0,
        output_pressure=0.5
    )
    return make_record_row(
        **dict(default_columns, **kwargs)
    )


def make_record_single_measure_row(**kwargs):
    default_columns = dict(
        id=1,
        time=datetime.fromisoformat('2024-09-30 20:23:40.000000000'),
        measure_name='my_metric',
        my_metric_double=0.5
    )
    return make_record_row(
        **dict(default_columns, **kwargs)
    )


def make_write_record_multi_measure(**kwargs) -> RecordTypeDef:
    default_params = dict(
        time=int(datetime.fromisoformat(
            '2024-09-30 20:23:40.000000000'
        ).replace(tzinfo=timezone.utc).timestamp() * 1000),
        dimensions={},
        measure_name='metrics',
        metrics={
            'string_value': 'test string',
            'id': 1,
            'input_pressure': 1.0,
            'output_pressure': 0.5
        }
    )
    params = dict(default_params, **kwargs)
    return {
        'Dimensions': [
            {'Name': dim_name, 'Value': str(dim_value)}
            for dim_name, dim_value in params['dimensions'].items()
        ],
        'Time': str(params['time']),
        'TimeUnit': 'MILLISECONDS',
        'MeasureName': 'metrics',
        'MeasureValueType': 'MULTI',
        'MeasureValues': [
            {
                'Name': metric_name,
                'Value': str(metric_value),
                'Type': RecordConverter.MEASURE_TYPE_NAME[type(metric_value)]
            } for metric_name, metric_value in params['metrics'].items()
            if metric_name not in params['dimensions']
        ]
    }


def make_write_record_single_measure(**kwargs) -> RecordTypeDef:
    default_params = dict(
        time=int(datetime.fromisoformat(
            '2024-09-30 20:23:40.000000000'
        ).replace(tzinfo=timezone.utc).timestamp() * 1000),
        dimensions={},
        measure_name='my_metric',
        metric_value=0.5,
        metric_value_type='DOUBLE'
    )
    params = dict(default_params, **kwargs)
    return {
        'Dimensions': [
            {'Name': dim_name, 'Value': str(dim_value)}
            for dim_name, dim_value in params['dimensions'].items()
        ],
        'Time': str(params['time']),
        'TimeUnit': 'MILLISECONDS',
        'MeasureName': str(params['measure_name']),
        'MeasureValueType': params['metric_value_type'],
        'MeasureValue': str(params['metric_value'])
    }
