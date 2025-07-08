# engine.py
"""Trace generation engine and OpenTelemetry setup with database integration."""

import logging
from typing import Dict, List
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanProcessor,
    ReadableSpan,
)
from opentelemetry.trace import StatusCode, SpanKind, Link
from trace_generator.config import Config
from trace_generator.resolver import ValueResolver
from trace_generator.database import get_database, DatabaseInterface, InMemoryDatabase
import random
import time
from threading import Thread, Lock
from collections import deque, OrderedDict
import fnmatch
import re
import atexit
from datetime import datetime, timezone


# Numeric status codes for ClickHouse and OTel
class NumericStatusCode:
    UNSET = 0
    OK = 1
    ERROR = 2


_trace_providers: List[TracerProvider] = []


class InMemorySpanProcessor(SpanProcessor):
    """Custom span processor that stores traces in the in-memory database."""

    def __init__(self, database: InMemoryDatabase):
        self.database = database
        self.logger = logging.getLogger(__name__)

    def on_start(self, span: ReadableSpan, parent_context) -> None:
        """Called when a span starts."""
        pass

    def on_end(self, span: ReadableSpan) -> None:
        """Called when a span ends - store it in the in-memory database."""
        try:
            # Convert span to trace dictionary format
            trace_dict = {
                "TraceId": format(span.get_span_context().trace_id, "032x"),
                "SpanId": format(span.get_span_context().span_id, "016x"),
                "ParentSpanId": format(span.parent.span_id, "016x")
                if span.parent
                else "",
                "SpanName": span.name,
                "ServiceName": span.resource.attributes.get(
                    "service.name", "unknown-service"
                ),
                "StatusCode": span.status.status_code.name,
                "StatusMessage": span.status.description or "",
                "Timestamp": datetime.fromtimestamp(
                    span.start_time / 1_000_000_000, tz=timezone.utc
                ),
                "Duration": span.end_time - span.start_time,
                "SpanKind": span.kind.name,
                "SpanAttributes": dict(span.attributes) if span.attributes else {},
                "ResourceAttributes": dict(span.resource.attributes)
                if span.resource.attributes
                else {},
            }

            # Add the trace to the in-memory database
            self.database.add_trace(trace_dict)

        except Exception as e:
            self.logger.error(f"Error storing span in in-memory database: {e}")

    def shutdown(self) -> None:
        """Shutdown the processor."""
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush - no-op for in-memory processor."""
        return True


def setup_opentelemetry_providers(
    service_names: List[str], database: DatabaseInterface = None
) -> Dict[str, trace.Tracer]:
    """Setup OpenTelemetry TracerProviders with optional in-memory database integration."""
    global _trace_providers
    tracers = {}
    logger = logging.getLogger(__name__)

    # Get database instance if not provided
    if database is None:
        database = get_database()

    logger.info("Setting up OpenTelemetry TracerProviders for each service...")

    for service_name in service_names:
        resource = Resource(attributes={"service.name": service_name})
        provider = TracerProvider(resource=resource)

        # Always add OTLP exporter for the collector pipeline
        otlp_exporter = OTLPSpanExporter(endpoint=Config.OTLP_ENDPOINT, insecure=True)
        otlp_processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(otlp_processor)

        # If using in-memory database, also add the in-memory processor
        if isinstance(database, InMemoryDatabase):
            inmemory_processor = InMemorySpanProcessor(database)
            provider.add_span_processor(inmemory_processor)
            logger.debug(f"Added in-memory span processor for service: {service_name}")

        tracers[service_name] = provider.get_tracer(f"{service_name}-tracer", "1.0.0")
        _trace_providers.append(provider)
        logger.debug(f"Tracer created for service: {service_name}")

    return tracers


def shutdown_opentelemetry_providers():
    global _trace_providers
    logger = logging.getLogger(__name__)
    logger.info("Shutting down OpenTelemetry providers...")
    for provider in _trace_providers:
        try:
            provider.force_flush(timeout_millis=5000)
            provider.shutdown()
        except Exception as e:
            logger.warning(f"Error shutting down provider: {e}")
    _trace_providers.clear()


atexit.register(shutdown_opentelemetry_providers)


def set_span_status_ok(span):
    span.set_status(StatusCode.OK)
    span.set_attribute("otel.status_code", NumericStatusCode.OK)


def set_span_status_error(span, message: str, error_type: str):
    span.set_status(StatusCode.ERROR, message)
    span.set_attributes(
        {
            "otel.status_code": NumericStatusCode.ERROR,
            "otel.status_message": message,
            "error.type": error_type,
        }
    )


class TraceGenerator:
    def __init__(
        self,
        tracers: Dict[str, trace.Tracer],
        scenarios_config: Dict,
        num_workers: int = 4,
        database: DatabaseInterface = None,
    ):
        self.tracers = tracers
        self.scenarios = scenarios_config.get("scenarios", [])
        self.scenario_weights = OrderedDict()
        for i, scenario in enumerate(self.scenarios):
            self.scenario_weights[i] = scenario.get("weight", 1)
        self.running = False
        self.trace_count = 0
        self.threads = []  # List of worker threads
        self.num_workers = num_workers
        self.resolver = ValueResolver()
        self.resolver.MAX_TEMPLATE_ITERATIONS = (
            Config.MAX_TEMPLATE_ITERATIONS
        )  # Pass config to resolver
        self.database = database or get_database()

        context_store_size = self._calculate_context_store_size()
        self.context_store = deque(maxlen=context_store_size)
        self.context_store_lock = Lock()

        logger = logging.getLogger(__name__)
        logger.info(f"Auto-configured context store size: {context_store_size}")
        logger.info(f"Using database: {type(self.database).__name__}")

    def _calculate_context_store_size(self) -> int:
        export_scenarios = 0
        total_export_weight = 0
        total_weight = sum(self.scenario_weights.values())
        for i, scenario in enumerate(self.scenarios):
            if self._scenario_exports_context(scenario):
                export_scenarios += 1
                total_export_weight += scenario.get("weight", 1)
        if export_scenarios == 0:
            return 10
        export_percentage = (
            (total_export_weight / total_weight) if total_weight > 0 else 0
        )
        avg_interval = (Config.TRACE_INTERVAL_MIN + Config.TRACE_INTERVAL_MAX) / 2
        traces_per_minute = 60 / avg_interval
        exports_per_minute = traces_per_minute * export_percentage
        buffer_minutes = min(10, max(2, export_scenarios))
        calculated_size = int(exports_per_minute * buffer_minutes * 1.5)
        min_size = 20
        max_size = 1000
        optimal_size = max(min_size, min(calculated_size, max_size))
        logging.debug(
            f"Context store calculation: {export_scenarios} export scenarios, "
            f"{export_percentage:.1%} export rate, "
            f"{exports_per_minute:.1f} exports/min, "
            f"calculated: {calculated_size}, final: {optimal_size}"
        )
        return optimal_size

    def _scenario_exports_context(self, scenario: Dict) -> bool:
        root_span = scenario.get("root_span", {})
        return self._span_exports_context(root_span)

    def _span_exports_context(self, span_def: Dict) -> bool:
        if "export_context_as" in span_def:
            return True
        for call in span_def.get("calls", []):
            if self._span_exports_context(call):
                return True
        return False

    def start(self):
        if not self.running:
            self.running = True
            self.threads = []
            for i in range(self.num_workers):
                t = Thread(
                    target=self._generate_traces_loop, name=f"TraceGenWorker-{i + 1}"
                )
                t.daemon = True
                t.start()
                self.threads.append(t)
            logging.info(
                f"Trace generation engine started with {self.num_workers} workers!"
            )
            return True
        return False

    def stop(self):
        if self.running:
            self.running = False
            for t in self.threads:
                if t.is_alive():
                    t.join(timeout=5.0)
            self.threads = []
            logging.info("Trace generation engine stopped!")
            return True
        return False

    def get_status(self):
        return {
            "running": self.running,
            "trace_count": self.trace_count,
            "scenarios_loaded": len(self.scenarios),
            "services_configured": len(self.tracers),
            "database_type": type(self.database).__name__,
            "database_healthy": self.database.health_check()
            if hasattr(self.database, "health_check")
            else True,
        }

    def _generate_traces_loop(self):
        logging.info("Starting trace generation loop...")
        while self.running:
            try:
                self.trace_count += 1
                self._generate_single_trace()
                time.sleep(
                    random.uniform(Config.TRACE_INTERVAL_MIN, Config.TRACE_INTERVAL_MAX)
                )
            except Exception as e:
                logging.error(f"Error in generation loop: {e}", exc_info=True)
                time.sleep(1)
        logging.info("Trace generation loop stopped.")

    def _generate_single_trace(self):
        if not self.scenarios:
            return
        scenario_indices = list(self.scenario_weights.keys())
        weights = list(self.scenario_weights.values())
        selected_index = random.choices(scenario_indices, weights=weights, k=1)[0]
        scenario = self.scenarios[selected_index]
        root_span_def = scenario.get("root_span")
        if not root_span_def:
            return
        scenario_context = {}
        for key, val_template in scenario.get("vars", {}).items():
            scenario_context[key] = self.resolver.resolve(
                val_template, scenario_context
            )
        self._process_span_definition(
            root_span_def, scenario_context, parent_attributes={}
        )

    def _process_span_definition(
        self, span_def: Dict, scenario_context: Dict, parent_attributes: Dict
    ):
        service_name = span_def.get("service")
        tracer = self.tracers.get(service_name)
        if not tracer:
            logging.warning(f"No tracer found for service: {service_name}")
            return
        links, linked_context = [], {}
        if "link_from_context" in span_def:
            with self.context_store_lock:
                pattern = span_def["link_from_context"]
                compiled_pattern = fnmatch.translate(pattern)
                regex_pattern = re.compile(compiled_pattern)
                matching_keys = [
                    key for key, _ in self.context_store if regex_pattern.match(key)
                ]
                if matching_keys:
                    key_to_link = random.choice(matching_keys)
                    for i, (key, data) in enumerate(self.context_store):
                        if key == key_to_link:
                            _, (stored_span_context, stored_attributes) = (
                                self.context_store[i]
                            )
                            links.append(Link(context=stored_span_context))
                            linked_context = {
                                "linked": {"attributes": stored_attributes}
                            }
                            logging.debug(f"Created link from '{key_to_link}'")
                            break
        current_context = {
            "parent": {"attributes": parent_attributes},
            **scenario_context,
            **linked_context,
        }
        op_name = self.resolver.resolve(
            span_def.get("operation", "Unknown Op"), current_context
        )
        export_key = ""
        if "export_context_as" in span_def:
            export_key = self.resolver.resolve(
                span_def["export_context_as"], current_context
            )
            current_context["context_key"] = export_key
        resolved_attrs = {
            k: self.resolver.resolve(v, current_context)
            for k, v in span_def.get("attributes", {}).items()
        }
        resolved_attrs["service.name"] = service_name
        span_kind_str = span_def.get("kind", "INTERNAL").upper()
        span_kind = getattr(SpanKind, span_kind_str, SpanKind.INTERNAL)
        with tracer.start_as_current_span(op_name, kind=span_kind, links=links) as span:
            span.set_attributes(resolved_attrs)
            if export_key:
                with self.context_store_lock:
                    self.context_store.append(
                        (export_key, (span.get_span_context(), resolved_attrs))
                    )
                    logging.debug(f"Exported context as '{export_key}'")
            event_context = {**current_context, **resolved_attrs}
            for event_def in span_def.get("events", []):
                event_name = self.resolver.resolve(
                    event_def.get("name", "unnamed_event"), event_context
                )
                event_attrs = {
                    k: self.resolver.resolve(v, event_context)
                    for k, v in event_def.get("attributes", {}).items()
                }
                span.add_event(name=event_name, attributes=event_attrs)
            delay_range = None
            if "delay_ms" in span_def:
                delay_ms_range = span_def["delay_ms"]
                if delay_ms_range[0] > 0 or delay_ms_range[1] > 0:
                    delay_range = [
                        delay_ms_range[0] / 1000.0,
                        delay_ms_range[1] / 1000.0,
                    ]
                    logging.debug(
                        f"Using delay_ms: {delay_ms_range}ms -> {delay_range}s"
                    )
            elif "delay" in span_def:
                delay_range = span_def["delay"]
                logging.debug(f"Using legacy delay: {delay_range}s")
            if delay_range and (delay_range[0] > 0 or delay_range[1] > 0):
                sleep_duration = random.uniform(*delay_range)
                time.sleep(sleep_duration)
            is_error = False
            error_conditions = span_def.get("error_conditions", [])
            if error_conditions:
                for error_cond in error_conditions:
                    probability_percent = error_cond.get("probability", 0)
                    random_percent = random.randint(1, 100)
                    if random_percent <= probability_percent:
                        error_type = error_cond.get("type", "UnknownError")
                        error_message = error_cond.get("message", "An error occurred")
                        set_span_status_error(span, error_message, error_type)
                        is_error = True
                        logging.debug(
                            f"Generated error ({probability_percent}% chance, rolled {random_percent}): {error_type} - {error_message}"
                        )
                        break
            if not is_error:
                set_span_status_ok(span)
            if not is_error:
                for child_span_def in span_def.get("calls", []):
                    self._process_span_definition(
                        child_span_def,
                        scenario_context,
                        parent_attributes=resolved_attrs,
                    )
