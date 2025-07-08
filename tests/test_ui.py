import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest
from unittest import mock
import asyncio


# Dummy config for UI
class DummyConfig:
    OTLP_ENDPOINT = "dummy-endpoint"
    CLICKHOUSE_HOST = "dummy-host"
    CLICKHOUSE_PORT = 9000
    STATUS_UPDATE_INTERVAL = 1
    CARD_DISPLAY_LIMIT = 2


# Patch Config in ui
@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    monkeypatch.setattr("trace_generator.ui.Config", DummyConfig)


# Patch NiceGUI ui
@pytest.fixture(autouse=True)
def patch_nicegui(monkeypatch):
    class DummyBuilder(mock.Mock):
        def classes(self, *a, **kw):
            return self

        def bind_visibility_from(self, *a, **kw):
            return self

        def add_slot(self, *a, **kw):
            return None

        def clear(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    dummy_ui = mock.Mock()
    dummy_ui.label = lambda *a, **kw: DummyBuilder()
    dummy_ui.header = dummy_ui.row = dummy_ui.column = dummy_ui.card = dummy_ui.icon = (
        dummy_ui.table
    ) = dummy_ui.dialog = dummy_ui.spinner = lambda *a, **kw: DummyBuilder()
    dummy_ui.page_title = dummy_ui.timer = dummy_ui.button = (
        lambda *a, **kw: DummyBuilder()
    )
    dummy_ui.toggle = lambda *a, **kw: DummyBuilder()
    dummy_ui.notify = lambda *a, **kw: None
    dummy_ui.page = lambda *a, **kw: lambda f: f
    dummy_ui.run = lambda **kw: None
    monkeypatch.setitem(sys.modules, "nicegui", mock.Mock(ui=dummy_ui))
    monkeypatch.setitem(sys.modules, "nicegui.ui", dummy_ui)
    monkeypatch.setattr("trace_generator.ui.ui", dummy_ui)
    return dummy_ui


def make_traceui():
    import trace_generator.ui as ui_module

    DummyTG = type(
        "DummyTG",
        (),
        {
            "get_status": lambda self: {
                "running": True,
                "trace_count": 5,
                "services_configured": 2,
            },
            "start": lambda self: True,
            "stop": lambda self: True,
        },
    )
    DummyDS = type(
        "DummyDS",
        (),
        {
            "fetch_unique_traces": lambda self: [
                {
                    "StatusCode": "OK",
                    "ServiceName": "svc",
                    "SpanName": "span",
                    "ShortTraceId": "t1",
                    "ShortSpanId": "s1",
                    "FormattedTime": "now",
                    "DurationMs": 1,
                    "KeyInfo": "info",
                },
                {
                    "StatusCode": "ERROR",
                    "ServiceName": "svc2",
                    "SpanName": "span2",
                    "ShortTraceId": "t2",
                    "ShortSpanId": "s2",
                    "FormattedTime": "now",
                    "DurationMs": 2,
                    "KeyInfo": "info2",
                    "StatusMessage": "fail",
                },
            ],
            "get_database_info": lambda self: {"type": "dummy"},
        },
    )
    return ui_module.TraceUI(
        DummyTG(),
        {"scenarios": [{"name": "A", "weight": 1}], "services": ["svc"]},
        trace_data_service=DummyDS(),
    )


def test_traceui_init_and_status():
    traceui = make_traceui()
    assert traceui.status_label is None
    asyncio.run(traceui.update_status())


def test_traceui_update_status_sets_label():
    traceui = make_traceui()

    class DummyLabel:
        def __init__(self):
            self.text = ""

    traceui.status_label = DummyLabel()
    asyncio.run(traceui.update_status())
    assert (
        "Running" in traceui.status_label.text or "Stopped" in traceui.status_label.text
    )


def test_create_main_page_runs():
    traceui = make_traceui()
    traceui.create_main_page()


def test_create_control_panel_runs():
    traceui = make_traceui()
    traceui._create_control_panel()


def test_create_configuration_display_runs():
    traceui = make_traceui()
    traceui._create_configuration_display()


def test_create_trace_viewer_runs():
    traceui = make_traceui()
    traceui._create_trace_viewer()


def test_create_trace_card_success_and_error():
    traceui = make_traceui()
    traceui._create_trace_card(
        {
            "StatusCode": "OK",
            "ServiceName": "svc",
            "SpanName": "span",
            "ShortTraceId": "t1",
            "ShortSpanId": "s1",
            "FormattedTime": "now",
            "DurationMs": 1,
            "KeyInfo": "info",
        }
    )
    traceui._create_trace_card(
        {
            "StatusCode": "ERROR",
            "ServiceName": "svc2",
            "SpanName": "span2",
            "ShortTraceId": "t2",
            "ShortSpanId": "s2",
            "FormattedTime": "now",
            "DurationMs": 2,
            "KeyInfo": "info2",
            "StatusMessage": "fail",
        }
    )


def test_create_trace_card_edge_cases():
    traceui = make_traceui()
    # No StatusCode
    traceui._create_trace_card(
        {
            "ServiceName": "svc",
            "SpanName": "span",
            "ShortTraceId": "t1",
            "ShortSpanId": "s1",
            "FormattedTime": "now",
            "DurationMs": 1,
        }
    )
    # StatusCode not OK/ERROR
    traceui._create_trace_card(
        {
            "StatusCode": "UNKNOWN",
            "ServiceName": "svc",
            "SpanName": "span",
            "ShortTraceId": "t1",
            "ShortSpanId": "s1",
            "FormattedTime": "now",
            "DurationMs": 1,
        }
    )
    # No KeyInfo
    traceui._create_trace_card(
        {
            "StatusCode": "OK",
            "ServiceName": "svc",
            "SpanName": "span",
            "ShortTraceId": "t1",
            "ShortSpanId": "s1",
            "FormattedTime": "now",
            "DurationMs": 1,
        }
    )
    # No FormattedTime/DurationMs
    traceui._create_trace_card(
        {
            "StatusCode": "OK",
            "ServiceName": "svc",
            "SpanName": "span",
            "ShortTraceId": "t1",
            "ShortSpanId": "s1",
        }
    )


def test_create_configuration_display_empty():
    import trace_generator.ui as ui_module

    DummyTG = type(
        "DummyTG",
        (),
        {
            "get_status": lambda self: {
                "running": True,
                "trace_count": 5,
                "services_configured": 2,
            }
        },
    )
    traceui = ui_module.TraceUI(DummyTG(), {"scenarios": [], "services": []})
    traceui._create_configuration_display()


@pytest.mark.asyncio
def test_start_generation_and_stop_generation():
    traceui = make_traceui()
    # start_generation
    asyncio.run(traceui.start_generation())

    # stop_generation (simulate async and error)
    async def fail_stop():
        raise Exception("fail")

    traceui.trace_generator.stop = fail_stop
    with mock.patch("trace_generator.ui.ui.notify") as notify_mock:
        asyncio.run(traceui.stop_generation())
        assert notify_mock.called


@pytest.mark.asyncio
def test_maybe_async_sync_and_async():
    traceui = make_traceui()

    def sync_func(x):
        return x + 1

    async def async_func(x):
        return x + 2

    assert asyncio.run(traceui._maybe_async(sync_func, 1)) == 2
    assert asyncio.run(traceui._maybe_async(async_func, 1)) == 3


@pytest.mark.asyncio
def test_fetch_traces_all_paths():
    traceui = make_traceui()
    # No trace_data_service
    traceui.trace_data_service = None
    asyncio.run(traceui.fetch_traces())
    # With trace_data_service, with traces
    traceui = make_traceui()
    traceui.trace_cards_container = mock.Mock()
    traceui.trace_table = mock.Mock(rows=[], update=lambda: None)
    traceui.span_context_table = mock.Mock(rows=[], update=lambda: None)
    asyncio.run(traceui.fetch_traces())

    # With trace_data_service, but fetch_unique_traces raises
    class BadDS:
        def fetch_unique_traces(self):
            raise Exception("fail")

    traceui.trace_data_service = BadDS()
    with mock.patch("trace_generator.ui.logger") as logger_mock:
        asyncio.run(traceui.fetch_traces())
        assert logger_mock.error.called


@pytest.mark.asyncio
def test_fetch_traces_empty_and_error():
    traceui = make_traceui()

    # Empty traces
    class EmptyDS:
        def fetch_unique_traces(self):
            return []

        def get_database_info(self):
            return {"type": "dummy"}

    traceui.trace_data_service = EmptyDS()
    traceui.trace_cards_container = mock.Mock()
    traceui.trace_table = mock.Mock(rows=[], update=lambda: None)
    traceui.span_context_table = mock.Mock(rows=[], update=lambda: None)
    asyncio.run(traceui.fetch_traces())

    # fetch_unique_traces raises
    class BadDS:
        def fetch_unique_traces(self):
            raise Exception("fail")

        def get_database_info(self):
            return {"type": "dummy"}

    traceui.trace_data_service = BadDS()
    with mock.patch("trace_generator.ui.logger") as logger_mock:
        asyncio.run(traceui.fetch_traces())
        assert logger_mock.error.called


@pytest.mark.asyncio
def test_stop_generation_already_stopped():
    traceui = make_traceui()

    async def stopped():
        return False

    traceui.trace_generator.stop = stopped
    with mock.patch("trace_generator.ui.ui.notify") as notify_mock:
        asyncio.run(traceui.stop_generation())
        assert notify_mock.called


@pytest.mark.asyncio
def test_stop_generation_exception():
    traceui = make_traceui()

    async def fail():
        raise Exception("fail")

    traceui.trace_generator.stop = fail
    with mock.patch("trace_generator.ui.ui.notify") as notify_mock:
        asyncio.run(traceui.stop_generation())
        assert notify_mock.called


@pytest.mark.asyncio
def test_start_generation_already_running():
    traceui = make_traceui()
    traceui.trace_generator.start = lambda: False
    with mock.patch("trace_generator.ui.ui.notify") as notify_mock:
        asyncio.run(traceui.start_generation())
        assert notify_mock.called


# Cover span_context_table slot logic (no-op, but for coverage)
def test_create_trace_viewer_slot_coverage():
    traceui = make_traceui()
    traceui._create_trace_viewer()
    # Simulate slot call
    if hasattr(traceui, "span_context_table"):
        traceui.span_context_table.add_slot("body-row", "<q-tr></q-tr>")
