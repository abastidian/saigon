"""
A set of utilities to enable structured context-aware logging in your application.

This module provides multiple utilities to incorporate context-aware logging in as many parts
of your code as possible. The main construct, logcontext, allows you to create a local
scoped context to define key-value items that will be appended all log messages generated under
this context. Key-value items are automatically removed after exiting the context, hence log
messages outside of it will not contain them.

See the following basic example::

    import logging
    import logutils
    ...

    logutils.enable_log_context()
    logger = logging.getLogger()
    ...

    logger.info('before context')
    with logutils.log_context():
        set_log_context(my_key='value')
        logger.info('in context')

    logger.info('after context')


The above code will produce the following log messages (omitting some values)::

{"message": "before context", "level": "INFO", ...}
{"message": "in context", "my_key': "value", "level": "INFO", ...}
{"message": "after context", "level": "INFO", ...}

Note how only the second log–the one in the context and after set the key–contains the key
item ``my_key``. Additionally, the format of the log messages is JSON, a feature also provided
as part of enabling context logging.

Using Context Logging
---------------------

Three steps are needed to enable and use context logging:

1. Enable structured context logging for the built-in Python logger with
   enable_log_context.

2. Create a local scoped context to add log key items.

3. Set/Unset key items under your context.


Understanding Scopes
--------------------

Logging contexts are implemented as :class:`contextlib::AbstractContextManager` using
``contextvars::ContextVar``. This implementation allows to create self-managed contexts with
top-down items visibility. That is, key items set in an outer scope are passed down to its
inner scopes, which in addition can not only set newer keys but also override any of the keys
from the outer scope. Then, when the inner scope exits, the outer scope is restored to the
original keys that were set prior to the creation of the inner scope.

Let's look at the following example to understand this behavior. We'll use explicit context
creation for clarity, but the behavior is equally applicable with the decorator.

For example::

    with logutils.logcontext():
        logger.info('start of outer scope')
        set_log_context(outer1='value1', outer2='value2')
        with logutils.logcontext():
            # start of inner log context scope
            set_log_context(inner='value3', outer2='override')
            logger.info('showing inner scope')
        logger.info('end of outer scope')

The generated log messages (some content omitted)::

    {"message": "start of outer scope", "outer1": "value1", "outer2":"value2" }
    {"message": "showing inner scope", outer1": "value1", "outer2": "override", "inner": "value3" }
    {"message": "start of outer scope", "outer1": "value1", "outer2": "value2" }

Notice how the first and third logs have the same key items, even though the inner scope
overrides one of them (``outer2``) as well sets a new item (``inner``), as shown in the second log.
These changes are shown in the second log, which also contains the outer scope item

Multithreading
--------------

The use of the logging context is thread-safe since a new underlying context is created for each
thread. The aspect to keep in mind is that children threads do not inherit the key items of their
parent's thread, nor new items defined by children threads are passed to the parent.

This contrasts with coroutines, in which the context is passed down from the parent task to its
children, but no the other way around. This is the similar behavior shown above in regard
to outer and inner scopes.

Async Support
-------------
In order to use context logging in your async functions use the ``asynclogcontext`` decorator,
which provides the same construct as ``logcontext`` but for ``async`` functions.

"""

__all__ = [
    'logcontext',
    'asynclogcontext',
    'enable_log_context',
    'set_log_context',
    'unset_log_context'
]

import logging
from typing import Optional, Self
from contextvars import ContextVar
from contextlib import (
    AbstractContextManager,
    ContextDecorator,
    AbstractAsyncContextManager,
    AsyncContextDecorator
)

import pythonjsonlogger.json as json_logger
from pythonjsonlogger.core import RESERVED_ATTRS

_LOG_CONTEXT = ContextVar('log-context', default={})
_LOG_CONTEXT_MGR = ContextVar('log-context-mgr')


class __ContextLogFilter(logging.Filter):
    """
    Implements a logging.Filter to append the
    current log context key items to the LogRecord.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        logging_context = _LOG_CONTEXT.get()
        for key, value in logging_context.items():
            record.__dict__[key] = value
        return True


_CONTEXT_LOG_FILTER = __ContextLogFilter()


def enable_log_context(log_prefix: Optional[str] = None):
    """
    Enables context logging support in your application. Typically, you'll
    call this function in the entry point of your application, before generating
    any logs.

    Enabling logging context also enables JSON formatting for the log messages. This
    is currently mandatory in order to use logging context.

    Args:
        log_prefix (Optional[str]): Optional prefix to be added to all logs, shown as a
            prompt delimited by colon before the JSON message.
    """
    json_formatter = json_logger.JsonFormatter(
        "%(name) %(levelname) %(asctime) %(message) %(funcName) %(lineno)",
        rename_fields={
            'levelname': 'level',
            'asctime': 'time',
            'funcName': 'func',
            'lineno': 'lineno',
        },
        json_ensure_ascii=False,
        prefix=f"{log_prefix}: " if log_prefix else '',
        reserved_attrs=RESERVED_ATTRS + ['taskName']
    )
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    is_missing_context_filter = True
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(json_formatter)
        handler.addFilter(_CONTEXT_LOG_FILTER)
        logger.handlers.append(handler)
        return

    for handler in logger.handlers:
        for set_filter in handler.filters:
            if isinstance(set_filter, __ContextLogFilter):
                is_missing_context_filter = False
                break

        if is_missing_context_filter:
            handler.addFilter(_CONTEXT_LOG_FILTER)

        if not isinstance(handler.formatter, json_logger.JsonFormatter):
            handler.setFormatter(json_formatter)


class logcontext(AbstractContextManager, ContextDecorator):
    """
    Creates a local scoped context to set log key items.

    There are two ways you can enable a managed scope:

    - Decorating your function with logcontext() (easiest and recommended):

    Example::

        @logcontext()
        def my_function():
            set_log_context(my_var='value')

    This method automatically generates a self-managed context applicable to the entire
    function scope. You can use set_log_contex() and unset_log_context() operations to
    add/remove keys, respectively, as needed.

    - Explicitly creating the scoped context anywhere in your code::

        def my_function():
            with logutils.logcontext() as lc:
                ...
                lc.set(my_key='value')
                ...

    Calling `set_log_context()` and `unset_log_context()` under the scope is equivalent
    as `lc.set()` and `lc.unset()`.

    The second method gives you more granularity defining the scopes at the expense of a
    bit more code overhead.

    """
    def __enter__(self) -> Self:
        self._previous_mgr_token = _LOG_CONTEXT_MGR.set(self)
        self._log_context = _LOG_CONTEXT.get().copy()
        self._previous_ctx_token = _LOG_CONTEXT.set(self._log_context)
        return self

    def __exit__(self, __exc_type, __exc_value, __traceback):
        _LOG_CONTEXT.reset(self._previous_ctx_token)
        _LOG_CONTEXT_MGR.reset(self._previous_mgr_token)

    def set(self, **kwargs):
        """
        Sets in the log context the specified key items as keywords::

            lc.set(key1='value1`, key2='value2`)

        The provided keys are set for the current context scope. Setting existing keys will
        override their value for the current context, and their previous value will be restored
        upon scope finalization.

        Args:
            kwargs: Custom keyword arguments representing the log keys. The value
                can be anything that is JSON serializable.
        """
        for key, value in kwargs.items():
            if value is not None:
                self._log_context[key] = value

    def unset(self, *args):
        """
        Removes the specified comma-separated list of key values, represented as strings::

            lc.unset('key1', 'key2')

        Removing a key from the current scope does not remove it from its parent/outer scope if
        it also sets it there.

        Args:
            args: List of keys to be removed as string arguments.
        """
        for key in args:
            self._log_context.pop(key)


class asynclogcontext(AbstractAsyncContextManager, AsyncContextDecorator):
    """Same as logcontext but for use on async functions.

    Example::

        @asynclogcontext()
        async def my_async_function():
            set_log_context(my_var='value')

    See:
        `logcontext`
    """
    def __init__(self):
        self._mgr = logcontext()

    async def __aenter__(self) -> Self:
        self._mgr.__enter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._mgr.__exit__(exc_type, exc_val, exc_tb)

    def set(self, **kwargs):
        self._mgr.set(**kwargs)

    def unset(self, *args):
        self._mgr.unset(*args)


def set_log_context(**kwargs):
    """
    Sets a list key items into the current log context.

    See:
        logcontext::set
    """
    ctx_mgr: logcontext = _LOG_CONTEXT_MGR.get()
    ctx_mgr.set(**kwargs)


def unset_log_context(*args):
    """
    Removes a set of key items from the current log context.

    See:
        logcontext::unset
    """
    ctx_mgr: logcontext = _LOG_CONTEXT_MGR.get()
    ctx_mgr.unset(*args)
