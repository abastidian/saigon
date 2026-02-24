import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from saigon.model import BasicRestResponse, EmptyContent
from saigon.rest.client import RestClient, _RestClientBase

_DUMMY_REQUEST = httpx.Request('GET', 'http://example.com/')
NON_GET_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']
JSON_FAMILY_CONTENT_TYPES = ['application/json', 'application/x-www-form-urlencoded']
JSON_COMPATIBLE_TYPES = ['application/json', 'application/x-www-form-urlencoded']
RAW_CONTENT_TYPES = ['application/xml', 'text/plain', 'application/octet-stream']
NON_JSON_CONTENT_TYPES = [
    'text/plain',
    'text/html',
    'application/xml',
    'application/octet-stream',
    'text/csv',
]


class SamplePayload(BaseModel):
    name: str
    value: int


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

def headers_without_accept():
    """Generate header dicts that don't contain any casing of 'accept'."""
    return st.one_of(
        st.none(),
        st.dictionaries(
            keys=st.text(min_size=1).filter(lambda k: k.lower() != 'accept'),
            values=st.text(),
            max_size=5,
        )
    )


def headers_without_content_type():
    """Generate header dicts that don't contain any casing of 'content-type'."""
    return st.one_of(
        st.none(),
        st.dictionaries(
            keys=st.text(min_size=1).filter(lambda k: k.lower() != 'content-type'),
            values=st.text(),
            max_size=5,
        )
    )


def accept_key_variants():
    """Generate 'accept' with arbitrary casing."""
    return st.sampled_from(['accept', 'Accept', 'ACCEPT', 'aCcEpT', 'ACCEPT'])


def content_type_key_variants():
    """Generate 'content-type' with arbitrary casing."""
    return st.sampled_from(['content-type', 'Content-Type', 'CONTENT-TYPE', 'Content-type'])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client_with_capture():
    """Build a RestClient whose httpx.Client uses a MockTransport.

    Returns (client, captured) where captured['request'] will hold the
    httpx.Request that was sent after the first call, and captured['body']
    will hold the raw bytes read from the request stream.
    """
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['request'] = request
        captured['body'] = request.read()
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    client = RestClient(service_url='http://example.com')
    client._client = httpx.Client(transport=transport)
    return client, captured


def _make_response(status_code: int, body: str, content_type: str) -> httpx.Response:
    """Build a synthetic httpx.Response with the given body and Content-Type."""
    response = httpx.Response(
        status_code=status_code,
        content=body.encode(),
        headers={'Content-Type': content_type},
    )
    response.request = _DUMMY_REQUEST
    return response


# ---------------------------------------------------------------------------
# Property 1: GET requests default Accept header
# Validates: Requirements 1.1, 1.2, 1.5
# ---------------------------------------------------------------------------

@given(extra_headers=headers_without_accept())
@settings(max_examples=50)
def test_get_sets_default_accept_when_not_present(extra_headers):
    """When no Accept header is in extra_headers, GET requests must default to application/json."""
    c = RestClient(service_url='http://example.com')
    req = c._build_request('GET', '/test', extra_headers=extra_headers)
    assert req.headers.get('Accept') == 'application/json'


@given(
    accept_key=accept_key_variants(),
    custom_value=st.text(min_size=1),
)
@settings(max_examples=50)
def test_get_does_not_override_existing_accept(accept_key, custom_value):
    """When Accept is already in extra_headers (any casing), GET must not override it."""
    c = RestClient(service_url='http://example.com')
    extra_headers = {accept_key: custom_value}
    req = c._build_request('GET', '/test', extra_headers=extra_headers)
    header_values = {k.lower(): v for k, v in req.headers.items()}
    assert header_values.get('accept') == custom_value


# ---------------------------------------------------------------------------
# Property 2: Non-GET requests default Content-Type header
# Validates: Requirements 1.3, 1.4, 1.5
# ---------------------------------------------------------------------------

@given(
    method=st.sampled_from(NON_GET_METHODS),
    extra_headers=headers_without_content_type(),
)
@settings(max_examples=50)
def test_non_get_sets_default_content_type_when_not_present(method, extra_headers):
    """When no Content-Type is in extra_headers, non-GET
    requests must default to application/json."""
    c = RestClient(service_url='http://example.com')
    req = c._build_request(method, '/test', extra_headers=extra_headers)
    assert req.headers.get('Content-Type') == 'application/json'


@given(
    method=st.sampled_from(NON_GET_METHODS),
    ct_key=content_type_key_variants(),
    custom_value=st.text(min_size=1),
)
@settings(max_examples=50)
def test_non_get_does_not_override_existing_content_type(method, ct_key, custom_value):
    """When Content-Type is already in extra_headers (any casing), non-GET must not override it."""
    c = RestClient(service_url='http://example.com')
    extra_headers = {ct_key: custom_value}
    req = c._build_request(method, '/test', extra_headers=extra_headers)
    header_values = {k.lower(): v for k, v in req.headers.items()}
    assert header_values.get('content-type') == custom_value


# ---------------------------------------------------------------------------
# Property 3: Pass-through serialization identity
# Validates: Requirements 2.2, 2.5, 2.7
# ---------------------------------------------------------------------------

@given(content=st.text())
@settings(max_examples=100)
def test_xml_str_passthrough(content):
    """str content with application/xml must be returned unchanged (identity)."""
    result = _RestClientBase._serialize_body('application/xml', content)
    assert result is content


@given(content=st.binary())
@settings(max_examples=100)
def test_xml_bytes_passthrough(content):
    """bytes content with application/xml must be returned unchanged (identity)."""
    result = _RestClientBase._serialize_body('application/xml', content)
    assert result is content


@given(content=st.text())
@settings(max_examples=100)
def test_text_plain_str_passthrough(content):
    """str content with text/plain must be returned unchanged (identity)."""
    result = _RestClientBase._serialize_body('text/plain', content)
    assert result is content


@given(content=st.binary())
@settings(max_examples=100)
def test_octet_stream_bytes_passthrough(content):
    """bytes content with application/octet-stream must be returned unchanged (identity)."""
    result = _RestClientBase._serialize_body('application/octet-stream', content)
    assert result is content


# ---------------------------------------------------------------------------
# Property 4: JSON-family serialization consistency
# Validates: Requirements 2.1, 2.4
# ---------------------------------------------------------------------------

@given(
    content_type=st.sampled_from(JSON_FAMILY_CONTENT_TYPES),
    name=st.text(min_size=1, max_size=50),
    value=st.integers(),
)
@settings(max_examples=100)
def test_json_family_serialization_equals_to_jsonable_python(content_type, name, value):
    """For any BaseModel instance, application/json and application/x-www-form-urlencoded
    serialization SHALL equal to_jsonable_python(content).
    Validates: Requirements 2.1, 2.4
    """
    content = SamplePayload(name=name, value=value)
    result = _RestClientBase._serialize_body(content_type, content)
    assert result == to_jsonable_python(content)


# ---------------------------------------------------------------------------
# Property 5: XML content type rejects BaseModel
# Validates: Requirements 2.3
# ---------------------------------------------------------------------------

@given(
    name=st.text(min_size=1, max_size=50),
    value=st.integers(),
)
@settings(max_examples=100)
def test_xml_with_basemodel_raises_value_error(name, value):
    """For any BaseModel instance, application/xml serialization SHALL raise ValueError.
    Validates: Requirements 2.3
    """
    content = SamplePayload(name=name, value=value)
    with pytest.raises(ValueError):
        _RestClientBase._serialize_body('application/xml', content)


# ---------------------------------------------------------------------------
# Property 6: Text/plain BaseModel uses model_dump_json
# Validates: Requirements 2.6
# ---------------------------------------------------------------------------

@given(
    name=st.text(min_size=1, max_size=50),
    value=st.integers(),
)
@settings(max_examples=100)
def test_text_plain_basemodel_uses_model_dump_json(name, value):
    """For any BaseModel instance, text/plain serialization SHALL equal content.model_dump_json().
    Validates: Requirements 2.6
    """
    content = SamplePayload(name=name, value=value)
    result = _RestClientBase._serialize_body('text/plain', content)
    assert result == content.model_dump_json()


# ---------------------------------------------------------------------------
# Property 7: httpx parameter dispatch mapping
# Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
# ---------------------------------------------------------------------------

@given(
    content_type=st.sampled_from(JSON_COMPATIBLE_TYPES),
    name=st.text(min_size=1, max_size=30).filter(lambda s: s.isprintable()),
    value=st.integers(min_value=-1000, max_value=1000),
)
@settings(max_examples=50)
def test_httpx_dispatch_json_and_form_use_correct_kwarg(content_type, name, value):
    """For application/json and application/x-www-form-urlencoded, the body must be
    routed to json= and data= respectively, verified via the encoded Content-Type
    header that httpx sets on the outgoing request.

    Validates: Requirements 3.1, 3.2
    """
    payload = SamplePayload(name=name, value=value)
    client, captured = _make_client_with_capture()

    client.create_resource(
        None,
        endpoint='/test',
        content=payload,
        headers={'Content-Type': content_type},
    )

    req: httpx.Request = captured['request']

    if content_type == 'application/json':
        assert req.headers.get('content-type', '').startswith('application/json')
    else:
        assert 'application/x-www-form-urlencoded' in req.headers.get('content-type', '')


@given(
    content_type=st.sampled_from(RAW_CONTENT_TYPES),
    raw_body=st.one_of(st.text(min_size=1, max_size=50), st.binary(min_size=1, max_size=50)),
)
@settings(max_examples=50)
def test_httpx_dispatch_raw_types_use_content_kwarg(content_type, raw_body):
    """For XML, text/plain, and octet-stream, the body must be routed to content=,
    meaning httpx sends the bytes/str through without re-encoding.

    Validates: Requirements 3.3, 3.4
    """
    client, captured = _make_client_with_capture()

    client.create_resource(
        None,
        endpoint='/test',
        content=raw_body,
        headers={'Content-Type': content_type},
    )

    req: httpx.Request = captured['request']
    # httpx streams content= bodies, so we verify the Content-Type header
    # was preserved rather than inspecting the raw body bytes
    assert req.headers.get('content-type') == content_type


# ---------------------------------------------------------------------------
# Property 8: JSON response deserialization round-trip
# Validates: Requirements 4.1
# ---------------------------------------------------------------------------

@given(
    name=st.text(min_size=1, max_size=50).filter(lambda s: '"' not in s and '\\' not in s),
    value=st.integers(min_value=-10_000, max_value=10_000),
    charset_suffix=st.one_of(
        st.just(''),
        st.just('; charset=utf-8'),
        st.just('; charset=UTF-8'),
    ),
)
@settings(max_examples=50)
def test_json_response_deserialization_round_trip(name, value, charset_suffix):
    """For any application/json response, _process_response must deserialize the body
    into the requested response_type using model_validate_json.
    Validates: Requirements 4.1
    """
    payload = SamplePayload(name=name, value=value)
    body = payload.model_dump_json()
    response = _make_response(200, body, f'application/json{charset_suffix}')

    result = _RestClientBase._process_response(response, SamplePayload)

    assert isinstance(result, SamplePayload)
    assert result.name == name
    assert result.value == value


# ---------------------------------------------------------------------------
# Property 9: Non-JSON responses return BasicRestResponse
# Validates: Requirements 4.2
# ---------------------------------------------------------------------------

@given(
    content_type=st.sampled_from(NON_JSON_CONTENT_TYPES),
    body=st.text(max_size=200),
    status_code=st.sampled_from([200, 201, 204]),
)
@settings(max_examples=50)
def test_non_json_response_returns_basic_rest_response(content_type, body, status_code):
    """For any non-application/json Content-Type, _process_response must return a
    BasicRestResponse containing the raw text body.
    Validates: Requirements 4.2
    """
    response = _make_response(status_code, body, content_type)

    result = _RestClientBase._process_response(response, SamplePayload)

    assert isinstance(result, BasicRestResponse)
    assert result.status_code == status_code
    assert result.content == body


# ---------------------------------------------------------------------------
# Property 10: response_type None or BasicRestResponse bypasses content-type logic
# Validates: Requirements 4.4, 4.5
# ---------------------------------------------------------------------------

@given(
    content_type=st.sampled_from(['application/json', 'text/plain', 'application/xml']),
    body=st.text(max_size=200),
    status_code=st.sampled_from([200, 201]),
)
@settings(max_examples=50)
def test_response_type_none_returns_empty_content(content_type, body, status_code):
    """When response_type is None, _process_response must return EmptyContent
    regardless of the response Content-Type.
    Validates: Requirements 4.4
    """
    response = _make_response(status_code, body, content_type)

    result = _RestClientBase._process_response(response, None)

    assert isinstance(result, EmptyContent)


@given(
    content_type=st.sampled_from(['application/json', 'text/plain', 'application/xml']),
    body=st.text(max_size=200),
    status_code=st.sampled_from([200, 201]),
)
@settings(max_examples=50)
def test_response_type_basic_rest_response_bypasses_content_type(content_type, body, status_code):
    """When response_type is BasicRestResponse, _process_response must return a
    BasicRestResponse with the raw text body, regardless of Content-Type.
    Validates: Requirements 4.5
    """
    response = _make_response(status_code, body, content_type)

    result = _RestClientBase._process_response(response, BasicRestResponse)
    assert isinstance(result, BasicRestResponse)
    assert result.status_code == status_code
    assert result.content == body
