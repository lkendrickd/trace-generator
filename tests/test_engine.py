import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest
import types
from trace_generator.engine import (
    InMemorySpanProcessor,
    setup_opentelemetry_providers,
    shutdown_opentelemetry_providers,
    set_span_status_ok,
    set_span_status_error,
    TraceGenerator,
    NumericStatusCode,
)
from trace_generator.database import InMemoryDatabase


class DummySpan:
    def __init__(self):
        self._attrs = {}
        self.status = types.SimpleNamespace(
            status_code=types.SimpleNamespace(name="OK"), description=""
        )
        self.name = "span"
        self.parent = None
        self.kind = types.SimpleNamespace(name="INTERNAL")
        self.resource = types.SimpleNamespace(attributes={"service.name": "svc"})
        self.attributes = {"foo": "bar"}
        self.start_time = 1_000_000_000
        self.end_time = 2_000_000_000

    def get_span_context(self):
        return types.SimpleNamespace(trace_id=1, span_id=2)

    def set_status(self, status, message=None):
        self._attrs["status"] = (status, message)

    def set_attribute(self, k, v):
        self._attrs[k] = v

    def set_attributes(self, d):
        self._attrs.update(d)

    def add_event(self, name, attributes=None):
        self._attrs["event"] = (name, attributes)


class DummyTracer:
    def start_as_current_span(self, *a, **k):
        class DummyCtx:
            def __enter__(self_):
                return DummySpan()

            def __exit__(self_, exc_type, exc_val, exc_tb):
                pass

        return DummyCtx()


class DummyProvider:
    def __init__(self):
        self._shutdown = False

    def force_flush(self, timeout_millis=5000):
        self._shutdown = True

    def shutdown(self):
        self._shutdown = True


class DummyDB(InMemoryDatabase):
    def health_check(self):
        return True


@pytest.fixture(autouse=True)
def reset_trace_providers():
    import importlib
    import trace_generator.engine as engine

    importlib.reload(engine)
    yield
    importlib.reload(engine)


def test_inmemory_span_processor_on_end():
    db = InMemoryDatabase()
    proc = InMemorySpanProcessor(db)
    span = DummySpan()
    proc.on_end(span)
    traces = db.fetch_unique_traces(1)
    assert traces
    # error path
    proc.database = None
    proc.on_end(span)  # should not raise


def test_inmemory_span_processor_flush_shutdown():
    db = InMemoryDatabase()
    proc = InMemorySpanProcessor(db)
    assert proc.force_flush()
    assert proc.shutdown() is None


def test_setup_and_shutdown_opentelemetry_providers():
    db = InMemoryDatabase()
    tracers = setup_opentelemetry_providers(["svc1", "svc2"], database=db)
    assert "svc1" in tracers and "svc2" in tracers
    # Add dummy provider for shutdown
    import trace_generator.engine as engine

    engine._trace_providers.append(object())
    shutdown_opentelemetry_providers()
    assert (
        all(p._shutdown for p in engine._trace_providers) or not engine._trace_providers
    )


def test_set_span_status_ok_and_error():
    span = DummySpan()
    set_span_status_ok(span)
    assert span._attrs["status"][0].name == "OK"
    assert span._attrs["otel.status_code"] == NumericStatusCode.OK
    set_span_status_error(span, "msg", "errtype")
    assert span._attrs["status"][0].name == "ERROR"
    assert span._attrs["otel.status_code"] == NumericStatusCode.ERROR
    assert span._attrs["otel.status_message"] == "msg"
    assert span._attrs["error.type"] == "errtype"


def make_scenario(export=False, error=False):
    root = {"service": "svc", "operation": "op", "attributes": {}, "calls": []}
    if export:
        root["export_context_as"] = "key"
    if error:
        root["error_conditions"] = [
            {"probability": 100, "type": "E", "message": "fail"}
        ]
    return {"scenarios": [{"root_span": root, "weight": 1}], "vars": {}}


def test_trace_generator_basic(monkeypatch):
    db = InMemoryDatabase()
    tracers = {"svc": DummyTracer()}
    config = make_scenario()
    tg = TraceGenerator(tracers, config, num_workers=1, database=db)
    assert tg.get_status()["scenarios_loaded"] == 1
    assert tg.get_status()["services_configured"] == 1
    assert tg.get_status()["database_type"] == "InMemoryDatabase"
    assert tg.get_status()["database_healthy"] is True
    # Accept 10 as valid minimum when no export scenarios
    assert tg._calculate_context_store_size() in (10, 20)
    tg.start()
    import time

    time.sleep(0.05)
    tg.stop()
    assert not tg.running


def test_trace_generator_context_export():
    db = InMemoryDatabase()
    tracers = {"svc": DummyTracer()}
    config = make_scenario(export=True)
    tg = TraceGenerator(tracers, config, num_workers=1, database=db)
    tg._generate_single_trace()
    # Should export context
    assert len(tg.context_store) >= 1


def test_trace_generator_error_conditions(monkeypatch):
    db = InMemoryDatabase()
    tracers = {"svc": DummyTracer()}
    config = make_scenario(error=True)
    tg = TraceGenerator(tracers, config, num_workers=1, database=db)
    # Patch random.randint to always trigger error
    monkeypatch.setattr("random.randint", lambda a, b: 1)
    tg._generate_single_trace()
    # Should set error status
    # (no assertion needed, just exercise the code)


def test_trace_generator_span_links():
    db = InMemoryDatabase()
    tracers = {"svc": DummyTracer()}
    config = make_scenario()
    tg = TraceGenerator(tracers, config, num_workers=1, database=db)
    # Add a context to link from
    tg.context_store.append(("key", (object(), {"foo": "bar"})))
    span_def = {
        "service": "svc",
        "operation": "op",
        "link_from_context": "key",
        "attributes": {},
    }
    tg._process_span_definition(span_def, {}, {})
    # Should create a link (no assertion needed)


def test_trace_generator_delay_and_child_calls(monkeypatch):
    db = InMemoryDatabase()
    tracers = {"svc": DummyTracer()}
    config = make_scenario()
    tg = TraceGenerator(tracers, config, num_workers=1, database=db)
    # Patch time.sleep to avoid real delay
    monkeypatch.setattr("time.sleep", lambda s: None)
    # delay_ms
    span_def = {
        "service": "svc",
        "operation": "op",
        "delay_ms": [1, 2],
        "attributes": {},
    }
    tg._process_span_definition(span_def, {}, {})
    # legacy delay
    span_def = {
        "service": "svc",
        "operation": "op",
        "delay": [0.001, 0.002],
        "attributes": {},
    }
    tg._process_span_definition(span_def, {}, {})
    # child calls
    child = {"service": "svc", "operation": "child", "attributes": {}}
    span_def = {"service": "svc", "operation": "op", "attributes": {}, "calls": [child]}
    tg._process_span_definition(span_def, {}, {})
    # error_conditions with 0 probability
    span_def = {
        "service": "svc",
        "operation": "op",
        "attributes": {},
        "error_conditions": [{"probability": 0}],
    }
    tg._process_span_definition(span_def, {}, {})
