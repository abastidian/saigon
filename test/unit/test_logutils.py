import json
import logging
from io import StringIO

import pytest

from saigon.logutils import (
    enable_log_context, logcontext, set_log_context, asynclogcontext
)

test_logger = logging.getLogger(__name__)


class LogMessageReader:
    def __init__(self, buffer: StringIO):
        self._buffer = buffer

    def read_log(self) -> dict:
        self._buffer.seek(0)
        return json.loads(self._buffer.readline())

    def clear(self):
        self._buffer.seek(0)
        self._buffer.truncate(0)


@pytest.fixture(autouse=True)
def log_reader() -> LogMessageReader:
    log_capture_string = StringIO()
    handler = logging.StreamHandler(log_capture_string)
    logging.getLogger().addHandler(handler)
    enable_log_context()
    return LogMessageReader(log_capture_string)


def assert_log_keys(
        log_reader: LogMessageReader,
        **kwargs
):
    log_message = log_reader.read_log()
    for key, value in kwargs.items():
        assert value == log_message.get(key, None)

    log_reader.clear()


class TestLoggingContext:

    def test_single_context_explicit(self, log_reader: LogMessageReader):
        parent_keys = dict(parent_key1='value1', parent_key2='value2')
        with logcontext() as lc:
            lc.set(**parent_keys)
            test_logger.info('after set')
            assert_log_keys(
                log_reader, message='after set', **parent_keys
            )
            log_reader.clear()
            lc.unset('parent_key2')
            test_logger.info('after unset parent_key2')
            assert_log_keys(
                log_reader,
                message='after unset parent_key2',
                parent_key1='value1',
                parent_key2=None
            )

        test_logger.info('after exit')
        assert_log_keys(
            log_reader,
            message='after exit',
            parent_key1=None,
            parent_key2=None
        )

    @classmethod
    def child_function(
            cls,
            log_reader: LogMessageReader,
            parent_keys: dict,
            **kwargs
    ) -> int:
        set_log_context(**kwargs)
        test_logger.info("decorated")
        assert_log_keys(
            log_reader,
            message="decorated",
            **dict(parent_keys, **kwargs)
        )
        return 1

    @logcontext()
    def decorated_function(
            self,
            log_reader: LogMessageReader,
            parent_keys: dict,
            **kwargs
    ) -> int:
        return self.child_function(log_reader, parent_keys, **kwargs)

    def test_single_context_decorated(self, log_reader):
        assert 1 == self.decorated_function(
            log_reader, parent_keys={}, decor_key='dc1'
        )

    @pytest.mark.parametrize(
        'parent_key',
        [None, 'value1']
    )
    def test_child_context_decorated(self, log_reader, parent_key):
        test_logger.info('at enter')
        assert_log_keys(log_reader, message='at enter')
        with logcontext():
            set_log_context(parent_key=parent_key)
            test_logger.info('after set')
            assert_log_keys(
                log_reader, message='after set', parent_key=parent_key
            )
            assert 1 == self.decorated_function(
                log_reader,
                parent_keys=dict(parent_key=parent_key),
                decor_key='dc1'
            )
            test_logger.info('after decorated')
            assert_log_keys(
                log_reader,
                message='after decorated',
                parent_key=parent_key,
                decor_key=None
            )

        test_logger.info('at exit')
        assert_log_keys(
            log_reader,
            message='at exit',
            parent_key=None,
            decor_key=None
        )

    def test_child_context_override_key(self, log_reader):
        parent_keys = dict(parent_key1='value1', parent_key2='value2')
        with logcontext():
            set_log_context(**parent_keys)
            self.decorated_function(
                log_reader,
                parent_keys=parent_keys,
                parent_key1='override'
            )
            test_logger.info('after override')
            assert_log_keys(log_reader, **dict(parent_keys, parent_key1='value1'))

        test_logger.info('after exit')
        assert_log_keys(
            log_reader, message='after exit', parent_key1=None, parent_key2=None
        )

    @pytest.mark.parametrize(
        'parent_key',
        [None, 'value1']
    )
    @pytest.mark.asyncio
    async def test_async_child_context(self, log_reader, parent_key):
        @asynclogcontext()
        async def decorated_async(
                parent_keys: dict,
                **kwargs
        ) -> int:
            return self.child_function(
                log_reader, parent_keys, **kwargs
            )

        parent_keys = dict(parent_key=parent_key)
        with logcontext() as lc:
            lc.set(**parent_keys)
            test_logger.info('after parent set')
            assert_log_keys(
                log_reader, message='after parent set', **parent_keys
            )
            await decorated_async(
                parent_keys=parent_keys, akey='ak1'
            )
            test_logger.info('after child exit')
            assert_log_keys(
                log_reader, message='after child exit', **parent_keys
            )
