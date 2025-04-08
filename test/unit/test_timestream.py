from typing import Optional, Tuple, Type
import typing

import pytest

from saigon.aws.timestream import (
    SingleMeasureConverter,
    MultiMeasureConverter,
    ModelTypeDef
)

from test.unit.fixtures import (
    RecordMultiMeasureSample,
    RecordSingleMeasureSampleGeneric,
    RecordSingleMeasureSampleCustom,
    make_multi_measure_sample,
    make_single_measure_sample_generic,
    make_single_measure_sample_custom,
    make_record_multi_measure_row,
    make_record_single_measure_row,
    make_record_row,
    make_write_record_multi_measure,
    make_write_record_single_measure
)


class TestRecordConverterFromRecord:

    @pytest.mark.parametrize(
        'expected, record_columns',
        [
            pytest.param(
                make_multi_measure_sample(),
                make_record_multi_measure_row(),
                id='default column match'
            )
        ]
    )
    def test_read_multi_measure(
            self, expected, record_columns: dict
    ):
        converter = MultiMeasureConverter(RecordMultiMeasureSample)
        result = converter.from_record(
            record_columns[0],
            record_columns[1]
        )
        assert expected == result

    @pytest.mark.parametrize(
        'record_columns',
        [
            pytest.param(
                make_record_multi_measure_row(measure_name='metrics_other'),
                id='different measure name field'
            ),
            pytest.param(
                make_record_row(some_field='value'),
                id='missing required fields'
            )
        ]
    )
    def test_read_multi_measure_invalid(
            self, record_columns: dict
    ):
        converter = MultiMeasureConverter(
            RecordMultiMeasureSample
        )
        with pytest.raises(ValueError):
            converter.from_record(
                record_columns[0],
                record_columns[1]
            )

    @pytest.mark.parametrize(
        'expected, record_columns, metric_spec',
        [
            pytest.param(
                make_single_measure_sample_generic(),
                make_record_single_measure_row(),
                ('name', 'value'),
                id='generic sample'
            ),
            pytest.param(
                make_single_measure_sample_custom(),
                make_record_single_measure_row(),
                None,
                id='custom sample'
            )
        ]
    )
    def test_read_single_measure(
            self, expected: ModelTypeDef, record_columns: dict, metric_spec: Tuple[str, str]
    ):
        converter = SingleMeasureConverter(
            expected.__class__,
            metric_name_field=metric_spec[0] if metric_spec else None,
            metric_value_field=metric_spec[1] if metric_spec else None
        )
        result = converter.from_record(
            record_columns[0],
            record_columns[1]
        )
        assert result == expected

    @pytest.mark.parametrize(
        'record_columns, metric_spec, sample_type',
        [
            pytest.param(
                make_record_single_measure_row(),
                None,
                RecordSingleMeasureSampleGeneric,
                id='invalid metric spec - unspecified'
            ),
            pytest.param(
                make_record_single_measure_row(),
                ('name', None),
                RecordSingleMeasureSampleGeneric,
                id='invalid metric spec - missing value field'
            ),
            pytest.param(
                make_record_single_measure_row(),
                ('invalid', 'invalid'),
                RecordSingleMeasureSampleGeneric,
                id='invalid metric spec - invalid values'
            ),
            pytest.param(
                make_record_single_measure_row(unknown_field='unknown'),
                None,
                RecordSingleMeasureSampleGeneric,
                id='unknown field'
            ),
            pytest.param(
                make_record_single_measure_row(unknown_field='unknown'),
                None,
                RecordSingleMeasureSampleCustom,
                id='unknown field'
            )
        ]
    )
    def test_read_single_measure_invalid(
            self,
            record_columns: dict,
            metric_spec: Tuple[str, str],
            sample_type: Type[ModelTypeDef]
    ):
        converter = SingleMeasureConverter(
            sample_type,
            metric_name_field=metric_spec[0] if metric_spec else None,
            metric_value_field=metric_spec[1] if metric_spec else None
        )
        with pytest.raises(ValueError):
            converter.from_record(
                record_columns[0],
                record_columns[1]
            )


class TestRecordConverterToRecord:
    @pytest.mark.parametrize(
        'write_params, data, partition_key',
        [
            pytest.param(
                dict(),
                make_multi_measure_sample(),
                None,
                id='default conversion'
            ),
            pytest.param(
                dict(dimensions={'id': 1}),
                make_multi_measure_sample(),
                None,
                id='id field as dimension'
            ),
            pytest.param(
                dict(dimensions={'id': 1, 'string_value': 'test string'}),
                make_multi_measure_sample(),
                None,
                id='id and string_value as dimension'
            ),
            pytest.param(
                dict(dimensions={'id': 1}),
                make_multi_measure_sample(),
                ('id', True),
                id='id as partition key (serialized)'
            ),
            pytest.param(
                dict(metrics={
                    'string_value': 'test string',
                    'input_pressure': 1.0,
                    'output_pressure': 0.5
                }),
                make_multi_measure_sample(),
                ('id', False),
                id='id as partition key (not serialized)'
            )
        ]
    )
    def test_write_multi_measure(
            self,
            write_params: dict,
            data: RecordMultiMeasureSample,
            partition_key: Optional[Tuple[str, bool]]
    ):
        expected = make_write_record_multi_measure(**write_params)
        converter = MultiMeasureConverter(
            RecordMultiMeasureSample,
            extra_dimensions=[
                dim for dim, _ in write_params.get('dimensions', {}).items()
                if not partition_key or dim != partition_key[0]
            ],
            partition_key=partition_key[0] if partition_key else None,

        )
        result = converter.to_record(
            data,
            include_partition_key=partition_key[1] if partition_key else True
        )
        assert result == expected

    @pytest.mark.parametrize(
        'write_params, data, partition_key, converter_args',
        [
            pytest.param(
                dict(),
                make_single_measure_sample_generic(),
                None,
                {},
                id='sample generic default'
            ),
            pytest.param(
                dict(dimensions={'id': 1}),
                make_single_measure_sample_generic(),
                None,
                {},
                id='id as dimension'
            ),
            pytest.param(
                dict(dimensions={'id': 1}),
                make_single_measure_sample_generic(),
                ('id', True),
                {},
                id='id as partition key (serialized)'
            ),
            pytest.param(
                dict(),
                make_single_measure_sample_generic(),
                ('id', False),
                {},
                id='id as partition key (not serialized)'
            ),
            pytest.param(
                dict(),
                make_single_measure_sample_generic(),
                None,
                dict(metric_name_field='name'),
                id='sample generic explicit metric name field'
            ),
            pytest.param(
                dict(),
                make_single_measure_sample_generic(),
                None,
                dict(metric_name_field='name', metric_value_field='value'),
                id='sample generic explicit metric name and value fields'
            ),
            pytest.param(
                dict(),
                make_single_measure_sample_custom(),
                None,
                dict(metric_value_field='my_metric'),
                id='sample custom default'
            ),
        ]
    )
    def test_write_single_measure(
            self,
            write_params: dict,
            data: ModelTypeDef,
            partition_key: Optional[Tuple[str, bool]],
            converter_args: dict
    ):
        expected = make_write_record_single_measure(**write_params)
        converter = SingleMeasureConverter(
            type(data),
            extra_dimensions=[
                dim for dim, _ in write_params.get('dimensions', {}).items()
                if not partition_key or dim != partition_key[0]
            ],
            partition_key=partition_key[0] if partition_key else None,
            **converter_args

        )
        result = converter.to_record(
            data,
            include_partition_key=partition_key[1] if partition_key else True
        )
        assert result == expected

    @pytest.mark.parametrize(
        'record_params, param_overrides, converter_params',
        [
            pytest.param(
                dict(),
                dict(Version=1),
                dict(),
                id='add Version'
            ),
            pytest.param(
                dict(dimensions={'id': 0}),
                dict(Dimensions=[]),
                dict(extra_dimensions=['id']),
                id='override Dimensions'
            )
        ]
    )
    def test_write_param_override(
            self, record_params: dict, param_overrides: dict, converter_params: dict
    ):
        expected = make_write_record_multi_measure(
            **record_params
        )
        expected = dict(expected, **param_overrides)
        data = make_multi_measure_sample()
        converter = MultiMeasureConverter(
            type(data), **converter_params
        )
        result = converter.to_record(
            data,
            **param_overrides
        )
        assert result == expected
