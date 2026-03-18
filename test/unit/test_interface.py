from contextlib import contextmanager
from typing import Generator, Any
from saigon.interface import EventHandler


class ConcreteEventHandler(EventHandler[str, str]):
    @contextmanager
    def on_event(self, input_data: str) -> Generator[str, Any, Any]:
        yield f"processed: {input_data}"


class TestInterface:
    def test_event_handler_protocol(self):
        handler = ConcreteEventHandler()
        with handler.on_event("test") as result:
            assert result == "processed: test"

    def test_runtime_checkable(self):
        assert isinstance(ConcreteEventHandler(), EventHandler)
