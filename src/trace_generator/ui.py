# =========================================================================
#                               UI COMPONENTS
# =========================================================================
# NiceGUI-based UI for controlling and monitoring the trace generator
from typing import Optional, Dict
import asyncio
import logging
from nicegui import ui
from trace_generator.config import Config
from trace_generator.data import TraceDataService

logger = logging.getLogger(__name__)


class TraceUI:
    """Handles all UI-related functionality"""

    def __init__(
        self,
        trace_generator,
        scenarios_config: Dict,
        trace_data_service: TraceDataService = None,
    ):
        self.trace_generator = trace_generator
        self.scenarios_config = scenarios_config
        self.trace_data_service = trace_data_service
        self.status_label: Optional[ui.label] = None
        self.trace_table: Optional[ui.table] = None
        self.trace_cards_container: Optional[ui.column] = None

    async def update_status(self):
        if self.status_label:
            status = self.trace_generator.get_status()
            status_text = (
                f"{'🟢 Running' if status['running'] else '🔴 Stopped'} | "
                f"Traces: {status['trace_count']} | "
                f"Services: {status['services_configured']}"
            )
            self.status_label.text = status_text

    def create_main_page(self):
        ui.page_title("🔭 OTel Trace Generator Engine")
        with ui.header().classes(
            "bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg"
        ):
            with ui.row().classes("w-full items-center justify-between px-4"):
                ui.label("🔭 Trace Generator").classes("text-xl font-bold")
                self.status_label = ui.label("Loading...").classes("text-sm")
        with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-6"):
            self._create_control_panel()
            self._create_configuration_display()
            self._create_trace_viewer()
        ui.timer(Config.STATUS_UPDATE_INTERVAL, self.update_status)

    def _create_control_panel(self):
        with ui.card().classes("w-full"):
            ui.label("Controls").classes("text-lg font-semibold mb-4")
            with ui.row().classes("gap-4 items-center"):
                ui.button(
                    "Start",
                    icon="play_arrow",
                    color="positive",
                    on_click=self.start_generation,
                )
                ui.button(
                    "Stop", icon="stop", color="negative", on_click=self.stop_generation
                )

    async def start_generation(self):
        if self.trace_generator.start():
            ui.notify("Trace generation started!", type="positive")
        else:
            ui.notify("Trace generation is already running!", type="warning")
        await self.update_status()

    async def stop_generation(self):
        # Show a modal overlay with spinner and message
        with ui.dialog() as dialog, ui.card():
            ui.spinner(size="lg", color="primary")
            ui.label("Stopping trace generation... Please wait.")
        dialog.open()
        try:
            result = await self._maybe_async(self.trace_generator.stop)
            if result:
                ui.notify("Trace generation stopped.", type="info")
            else:
                ui.notify("Trace generation is already stopped!", type="warning")
        except Exception as e:
            ui.notify(f"Error stopping trace generation: {e}", type="negative")
        finally:
            dialog.close()
        await self.update_status()

    async def _maybe_async(self, func, *args, **kwargs):
        # Helper to await if func is async, else run in thread
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            from concurrent.futures import ThreadPoolExecutor

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                ThreadPoolExecutor(), lambda: func(*args, **kwargs)
            )

    def _create_configuration_display(self):
        with ui.card().classes("w-full"):
            ui.label("Current Configuration").classes("text-lg font-semibold mb-4")
            with ui.row().classes("gap-8 flex-wrap"):
                with ui.column():
                    ui.label("Environment").classes("font-medium text-orange-600")
                    ui.label(f"OTLP Endpoint: {Config.OTLP_ENDPOINT}").classes(
                        "font-mono"
                    )
                    ui.label(
                        f"ClickHouse: {Config.CLICKHOUSE_HOST}:{Config.CLICKHOUSE_PORT}"
                    ).classes("font-mono")
                with ui.column():
                    ui.label("Loaded Scenarios").classes("font-medium text-blue-600")
                    for scenario in self.scenarios_config.get("scenarios", []):
                        ui.label(
                            f"- {scenario.get('name')} (Weight: {scenario.get('weight', 1)})"
                        )
                with ui.column():
                    ui.label("Service Names").classes("font-medium text-green-700")
                    for service in self.scenarios_config.get("services", []):
                        ui.label(f"- {service}")

    async def fetch_traces(self):
        ui.notify("Fetching latest traces...", type="info", timeout=1000)
        try:
            if not self.trace_data_service:
                ui.notify("No trace data service available", type="negative")
                return

            # Use asyncio.to_thread to avoid blocking UI thread
            traces = await asyncio.to_thread(
                self.trace_data_service.fetch_unique_traces
            )
            if self.trace_cards_container:
                self.trace_cards_container.clear()
                with self.trace_cards_container:
                    if not traces:
                        with ui.card().classes("w-full text-center p-8"):
                            ui.icon("info", size="2rem", color="blue")
                            ui.label(
                                "No traces found. Is the generator running?"
                            ).classes("text-lg mt-2")
                    for trace in traces[: Config.CARD_DISPLAY_LIMIT]:
                        self._create_trace_card(trace)

            if self.trace_table:
                self.trace_table.rows = traces
                self.trace_table.update()

            # Update the span context table as well
            if hasattr(self, "span_context_table") and self.span_context_table:
                self.span_context_table.rows = traces
                self.span_context_table.update()

            error_count = len(
                [
                    t
                    for t in traces
                    if t.get("StatusCode", "").upper() not in ["OK", "STATUS_CODE_OK"]
                ]
            )
            ui.notify(
                f"Loaded {len(traces)} traces ({error_count} errors)",
                type="positive",
                timeout=2000,
            )
        except Exception as e:
            logger.error(f"Error fetching traces: {e}")
            ui.notify(f"Error fetching traces: {e}", type="negative")

    def _create_trace_card(self, trace):
        status_code = str(trace.get("StatusCode", "")).upper()
        is_success = status_code in ("OK", "STATUS_CODE_OK")
        card_class = "w-full mb-2 border-l-4 " + (
            "border-green-500" if is_success else "border-red-500"
        )
        with ui.card().classes(card_class):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("flex-grow"):
                    with ui.row().classes("items-center gap-2"):
                        if is_success:
                            ui.icon("check_circle", color="green")
                        else:
                            ui.icon("error", color="red")
                        ui.label(trace.get("ServiceName", "Unknown")).classes(
                            "font-semibold"
                        )
                        ui.label("•").classes("text-gray-400")
                        ui.label(trace.get("SpanName", "Unknown")).classes(
                            "text-gray-600"
                        )
                    if not is_success and trace.get("StatusMessage"):
                        ui.label(f"❌ {trace['StatusMessage']}").classes(
                            "text-sm text-red-600 font-medium mt-1"
                        )
                    with ui.row().classes("items-center gap-4 mt-1"):
                        ui.label(f"Trace: {trace['ShortTraceId']}").classes(
                            "text-xs font-mono text-blue-600"
                        )
                        ui.label(f"Span: {trace['ShortSpanId']}").classes(
                            "text-xs font-mono text-purple-600"
                        )
                    if trace.get("KeyInfo"):
                        ui.label(trace["KeyInfo"]).classes("text-sm mt-1 text-blue-600")
                with ui.column().classes("text-right"):
                    ui.label(trace.get("FormattedTime", "N/A")).classes(
                        "text-sm font-mono"
                    )
                    ui.label(trace.get("DurationMs", "N/A")).classes(
                        "text-xs text-gray-500"
                    )

    def _create_trace_viewer(self):
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between mb-4"):
                ui.label("Live Trace Viewer").classes("text-lg font-semibold")
                ui.button(
                    "Refresh Traces",
                    icon="refresh",
                    color="primary",
                    on_click=self.fetch_traces,
                )

            view_toggle = ui.toggle(
                ["cards", "table", "span-contexts"], value="cards"
            ).classes("mb-4")

            self.trace_cards_container = (
                ui.column()
                .classes("w-full gap-2")
                .bind_visibility_from(view_toggle, "value", value="cards")
            )
            with self.trace_cards_container:
                with ui.card().classes("w-full text-center p-8"):
                    ui.icon("info", size="2rem", color="blue")
                    ui.label('Click "Refresh Traces" to load data').classes(
                        "text-lg mt-2"
                    )

            table_columns = [
                {
                    "name": "FormattedTime",
                    "label": "Time",
                    "field": "FormattedTime",
                    "align": "left",
                },
                {
                    "name": "ServiceName",
                    "label": "Service",
                    "field": "ServiceName",
                    "align": "left",
                },
                {
                    "name": "SpanName",
                    "label": "Span",
                    "field": "SpanName",
                    "align": "left",
                },
                {
                    "name": "TraceId",
                    "label": "Trace ID",
                    "field": "TraceId",
                    "align": "left",
                },
                {
                    "name": "StatusCode",
                    "label": "Status",
                    "field": "StatusCode",
                    "align": "center",
                },
                {
                    "name": "StatusMessage",
                    "label": "Error Details",
                    "field": "StatusMessage",
                    "align": "left",
                },
                {
                    "name": "DurationMs",
                    "label": "Duration",
                    "field": "DurationMs",
                    "align": "right",
                },
            ]
            self.trace_table = (
                ui.table(columns=table_columns, rows=[], row_key="SpanId")
                .classes("w-full")
                .bind_visibility_from(view_toggle, "value", value="table")
            )
            self.trace_table.add_slot(
                "body-cell-StatusCode",
                """
                <q-td key="StatusCode" :props="props">
                  <q-badge :color="['OK', 'STATUS_CODE_OK'].includes((props.value || '').toUpperCase()) ? 'positive' : 'negative'"
                    :label="['STATUS_CODE_OK', 'OK'].includes((props.value || '').toUpperCase()) ? 'OK' : ((props.value || '').toUpperCase() === 'STATUS_CODE_ERROR' ? 'ERROR' : (props.value || 'N/A'))" />
                </q-td>
            """,
            )

            # New: Span Contexts Table
            span_context_columns = [
                {
                    "name": "TraceId",
                    "label": "Trace ID",
                    "field": "TraceId",
                    "align": "left",
                },
                {
                    "name": "SpanId",
                    "label": "Span ID",
                    "field": "SpanId",
                    "align": "left",
                },
                {
                    "name": "ParentSpanId",
                    "label": "Parent Span ID",
                    "field": "ParentSpanId",
                    "align": "left",
                },
                {
                    "name": "ServiceName",
                    "label": "Service",
                    "field": "ServiceName",
                    "align": "left",
                },
                {
                    "name": "SpanName",
                    "label": "Span",
                    "field": "SpanName",
                    "align": "left",
                },
            ]
            self.span_context_table = (
                ui.table(columns=span_context_columns, rows=[], row_key="SpanId")
                .classes("w-full")
                .bind_visibility_from(view_toggle, "value", value="span-contexts")
            )
            # Use different colors for Parent and Child rows
            self.span_context_table.add_slot(
                "body-row",
                """
                <q-tr :key="props.row.SpanId" :props="props" :class="props.row.ParentSpanId ? 'bg-blue-50' : 'bg-green-50'">
                  <q-td v-for="col in columns" :key="col.name" :props="props">
                    <span v-if="col.name === 'SpanId' || col.name === 'ParentSpanId'">
                      <q-badge v-if="props.row.ParentSpanId" color="blue" label="Parent" class="mr-2" />
                      {{ props.row[col.name] }}
                    </span>
                    <span v-else>{{ props.row[col.name] }}</span>
                  </q-td>
                </q-tr>
            """,
            )
