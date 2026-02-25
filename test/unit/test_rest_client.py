import json

import httpx
from pydantic import BaseModel

from saigon.rest.client import RestClient, _RestClientBase


class SamplePayload(BaseModel):
    name: str
    value: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_REQUEST = httpx.Request('GET', 'http://example.com/')


def _make_response(status_code: int, body: str, content_type: str) -> httpx.Response:
    """Build a synthetic httpx.Response with the given body and Content-Type."""
    response = httpx.Response(
        status_code=status_code,
        content=body.encode(),
        headers={'Content-Type': content_type},
    )
    response.request = _DUMMY_REQUEST
    return response


def _make_sync_client_with_capture():
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


# ===========================================================================
# Backward compatibility unit tests
# Validates: Requirements 6.1, 6.2, 6.3, 6.4
# ===========================================================================


def test_post_basemodel_no_extra_headers_sends_json():
    """POST with BaseModel and no extra_headers must send body via json= (application/json).

    Validates: Requirements 6.1, 6.2
    """
    payload = SamplePayload(name='alice', value=42)
    client, captured = _make_sync_client_with_capture()

    client.create_resource(None, endpoint='/items', content=payload)

    req: httpx.Request = captured['request']
    # httpx sets Content-Type to application/json when json= kwarg is used
    assert req.headers.get('content-type', '').startswith('application/json')
    # For json= kwarg, httpx eagerly encodes the body into req.content
    body = json.loads(captured['body'])
    assert body == {'name': 'alice', 'value': 42}


def test_get_no_extra_headers_includes_accept_json():
    """GET with no extra_headers must include Accept: application/json.

    Validates: Requirements 6.1, 6.3
    """
    client = RestClient(service_url='http://example.com')
    req = client._build_request('GET', '/items')
    assert req.headers.get('Accept') == 'application/json'


def test_json_response_with_response_type_deserializes_to_model():
    """JSON response with a response_type must deserialize to the model instance.

    Validates: Requirements 6.1, 6.2
    """
    payload = SamplePayload(name='bob', value=99)
    body = payload.model_dump_json()
    response = _make_response(200, body, 'application/json')

    result = _RestClientBase._process_response(response, SamplePayload)

    assert isinstance(result, SamplePayload)
    assert result.name == 'bob'
    assert result.value == 99
