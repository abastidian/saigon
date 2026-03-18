from datetime import datetime, timedelta
import pytest
from pydantic import BaseModel, ValidationError
from saigon.model import (
    BaseModelNoExtra, DataSet, QueryDataPaginationToken, QueryDataParams,
    Range, TimeRange, IntRange, UIntRange, FloatRange,
    EmptyContent
)


class TestModels:
    def test_base_model_no_extra(self):
        class MyModel(BaseModelNoExtra):
            name: str

        m = MyModel(name="test")
        assert m.name == "test"

        with pytest.raises(ValidationError):
            MyModel(name="test", extra="field")

    def test_dataset(self):
        class MyItem(BaseModel):
            id: int

        ds = DataSet[MyItem](data=[MyItem(id=1), MyItem(id=2)])
        assert len(ds.data) == 2
        assert ds.data[0].id == 1

    def test_query_data_pagination_token(self):
        token = QueryDataPaginationToken(query_id="qid", next_token=10)
        assert token.query_id == "qid"
        assert token.next_token == 10
        assert token.offset == 10

        token2 = QueryDataPaginationToken.from_offset("qid2", 20)
        assert token2.query_id == "qid2"
        assert token2.offset == 20

    def test_query_data_params(self):
        class Selection(BaseModel):
            filter: str

        params = QueryDataParams[Selection](
            max_count=10, query=Selection(filter="abc")
        )
        assert params.max_count == 10
        assert params.has_max_count() is True
        assert params.has_query_selection() is True
        assert params.has_pagination_token() is False
        assert params.query_selection.filter == "abc"

        encoded = params.encode_query_selection()

        token_params = QueryDataParams[Selection](
            query=QueryDataPaginationToken(query_id=encoded, next_token=5)
        )
        assert token_params.has_pagination_token() is True
        assert token_params.has_query_selection() is False

        decoded = token_params.decode_query_selection(Selection)
        assert decoded.filter == "abc"

    def test_query_data_params_camelcase(self):
        class Selection(BaseModel):
            my_field: str

        params = QueryDataParams[Selection](
            max_count=10, query=Selection(my_field="val")
        )
        url_params = params.url_params_dict(camel_case=True)
        # to_camelcase("max_count") -> "MaxCount"
        # selection keys: "my_field" -> "MyField"
        assert "MaxCount" in url_params
        assert url_params["MaxCount"] == 10
        assert url_params["MyField"] == "val"

    def test_range(self):
        r = Range[int](start=1, end=10)
        assert r.length == 9

        with pytest.raises(ValueError, match="Invalid negative range"):
            Range[int](start=10, end=1)

    def test_time_range(self):
        start = datetime(2023, 1, 1)
        end = datetime(2023, 1, 2)
        tr = TimeRange(start=start, end=end)
        assert tr.length() == timedelta(days=1)

        # Test default end (now)
        tr2 = TimeRange(start=start)
        assert tr2.end > start

    def test_int_range_defaults(self):
        ir = IntRange()
        assert ir.start == -(2**63)
        assert ir.end == 2**63 - 1

    def test_uint_range_defaults(self):
        uir = UIntRange()
        assert uir.start == 0
        assert uir.end == 2**64 - 1

    def test_float_range_defaults(self):
        fr = FloatRange()
        assert fr.start == float('-inf')
        assert fr.end == float('inf')

    def test_empty_content(self):
        ec = EmptyContent.model_validate(None)
        assert ec.model_dump() == {}

        ec2 = EmptyContent.model_validate({"a": 1})
        assert ec2.model_dump() == {}  # EmptyContent has no fields!
        # Wait, if it has no fields, model_dump() is {} anyway.
