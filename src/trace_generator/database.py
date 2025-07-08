# database.py
"""Database abstraction layer for trace data storage."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging
import os
from collections import deque
from datetime import datetime, timezone
import threading
import uuid


class DatabaseInterface(ABC):
    """Abstract interface for trace data storage backends."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the database. Returns True if successful."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close database connection."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the database is healthy and responsive."""
        pass

    @abstractmethod
    def fetch_unique_traces(self, limit: int) -> List[Dict[str, Any]]:
        """Fetch unique traces from the database."""
        pass

    @abstractmethod
    def get_trace_counts(self) -> Dict[str, int]:
        """Get trace count statistics."""
        pass

    @abstractmethod
    def get_service_names(self) -> List[str]:
        """Get list of service names from stored traces."""
        pass

    @abstractmethod
    def add_trace(self, trace: Dict[str, Any]) -> None:
        """Add a trace to the database (for in-memory and testing)."""
        pass


class ClickHouseDatabase(DatabaseInterface):
    """ClickHouse implementation of the database interface."""

    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.logger = logging.getLogger(__name__)
        self._client = None
        self.clickhouse_connect = None
        self.ch_exceptions = None

        # Import ClickHouse dependencies - don't fail if not available
        try:
            import clickhouse_connect
            from clickhouse_connect.driver import exceptions as ch_exceptions

            self.clickhouse_connect = clickhouse_connect
            self.ch_exceptions = ch_exceptions
        except ImportError:
            self.logger.warning(
                "ClickHouse dependencies not found. ClickHouse functionality will be limited."
            )
            # Don't raise - allow fallback to work

    def connect(self) -> bool:
        """Establish connection to ClickHouse."""
        if not self.clickhouse_connect:
            self.logger.error("ClickHouse dependencies not available")
            return False

        try:
            self._client = self.clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to ClickHouse: {e}")
            return False

    def disconnect(self) -> None:
        """Close ClickHouse connection."""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                self.logger.error(f"Error closing ClickHouse connection: {e}")
            finally:
                self._client = None

    def health_check(self) -> bool:
        """Check ClickHouse health."""
        if not self.clickhouse_connect:
            return False

        try:
            with self.clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            ) as client:
                client.query("SELECT 1")
                return True
        except Exception as e:
            self.logger.error(f"ClickHouse health check failed: {e}")
            return False

    def fetch_unique_traces(self, limit: int) -> List[Dict[str, Any]]:
        """Fetch unique traces from ClickHouse."""
        if not self.clickhouse_connect:
            return []

        try:
            with self.clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            ) as client:
                query = """
                    SELECT * FROM (
                        SELECT *, ROW_NUMBER() OVER (PARTITION BY TraceId ORDER BY CASE WHEN StatusCode = 'Error' THEN 1 ELSE 2 END, Timestamp DESC) as rn
                        FROM otel_traces ORDER BY Timestamp DESC
                    ) WHERE rn = 1 LIMIT %s
                """
                result = client.query(query, [limit])
                return self._process_query_results(result)
        except Exception as e:
            self.logger.error(f"Error fetching traces: {e}")
            return []

    def get_trace_counts(self) -> Dict[str, int]:
        """Get trace count statistics from ClickHouse."""
        if not self.clickhouse_connect:
            return {"total": 0, "errors": 0, "success": 0}

        try:
            with self.clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            ) as client:
                # Get total traces
                total_result = client.query(
                    "SELECT COUNT(DISTINCT TraceId) FROM otel_traces"
                )
                total_traces = (
                    total_result.result_rows[0][0] if total_result.result_rows else 0
                )

                # Get error traces
                error_result = client.query(
                    "SELECT COUNT(DISTINCT TraceId) FROM otel_traces WHERE StatusCode = 'Error'"
                )
                error_traces = (
                    error_result.result_rows[0][0] if error_result.result_rows else 0
                )

                return {
                    "total": total_traces,
                    "errors": error_traces,
                    "success": total_traces - error_traces,
                }
        except Exception as e:
            self.logger.error(f"Error getting trace counts: {e}")
            return {"total": 0, "errors": 0, "success": 0}

    def get_service_names(self) -> List[str]:
        """Get list of service names from ClickHouse."""
        if not self.clickhouse_connect:
            return []

        try:
            with self.clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            ) as client:
                result = client.query(
                    "SELECT DISTINCT ServiceName FROM otel_traces ORDER BY ServiceName"
                )
                return (
                    [row[0] for row in result.result_rows] if result.result_rows else []
                )
        except Exception as e:
            self.logger.error(f"Error getting service names: {e}")
            return []

    def add_trace(self, trace: Dict[str, Any]) -> None:
        """ClickHouse doesn't support direct trace addition (uses OTLP pipeline)."""
        self.logger.debug("ClickHouse trace insertion handled by OTLP pipeline")

    def _process_query_results(self, result) -> List[Dict[str, Any]]:
        """Process ClickHouse query results into dictionaries."""
        if not result.result_rows:
            return []

        columns = result.column_names
        traces = []

        for row in result.result_rows:
            trace_dict = dict(zip(columns, row))
            self._format_trace_data(trace_dict)
            traces.append(trace_dict)

        return traces

    def _format_trace_data(self, trace_dict: Dict[str, Any]) -> None:
        """Format trace data for UI display."""
        # Format timestamp for display
        if "Timestamp" in trace_dict and trace_dict["Timestamp"]:
            try:
                if hasattr(trace_dict["Timestamp"], "strftime"):
                    trace_dict["formatted_timestamp"] = trace_dict[
                        "Timestamp"
                    ].strftime("%Y-%m-%d %H:%M:%S")
                    trace_dict["FormattedTime"] = trace_dict["Timestamp"].strftime(
                        "%H:%M:%S"
                    )
                else:
                    trace_dict["formatted_timestamp"] = str(trace_dict["Timestamp"])
                    trace_dict["FormattedTime"] = str(trace_dict["Timestamp"])
            except Exception:
                trace_dict["formatted_timestamp"] = "Invalid Date"
                trace_dict["FormattedTime"] = "Invalid"
        else:
            trace_dict["formatted_timestamp"] = "No Timestamp"
            trace_dict["FormattedTime"] = "N/A"

        # Format duration
        if "Duration" in trace_dict:
            duration_ns = int(trace_dict["Duration"]) if trace_dict["Duration"] else 0
            duration_ms = duration_ns / 1_000_000
            if duration_ms < 1:
                trace_dict["DurationMs"] = f"{duration_ms:.2f}ms"
            else:
                trace_dict["DurationMs"] = f"{duration_ms:.1f}ms"
        else:
            trace_dict["DurationMs"] = "N/A"

        # Short IDs for display
        trace_dict["ShortTraceId"] = str(trace_dict.get("TraceId", "unknown"))[:16]
        trace_dict["ShortSpanId"] = str(trace_dict.get("SpanId", "unknown"))[:16]

        # Determine status color
        status_code = trace_dict.get("StatusCode", "")
        if status_code is None:
            status_code = ""
        status_code = str(status_code).upper()
        if status_code in ["OK", "STATUS_CODE_OK"]:
            trace_dict["status_color"] = "positive"
        else:
            trace_dict["status_color"] = "negative"


class InMemoryDatabase(DatabaseInterface):
    """In-memory database implementation using a thread-safe deque."""

    def __init__(self, max_traces: Optional[int] = None):
        self.max_traces = max_traces or int(os.getenv("INMEMORY_MAX_TRACES", "100"))
        self.traces = deque(maxlen=self.max_traces)
        self.lock = threading.RLock()  # Thread-safe access
        self.logger = logging.getLogger(__name__)
        self.logger.info(
            f"Initialized InMemory Database - max traces: {self.max_traces}"
        )

    def connect(self) -> bool:
        """In-memory connection always succeeds."""
        self.logger.info("InMemory database connection established")
        return True

    def disconnect(self) -> None:
        """In-memory disconnect."""
        with self.lock:
            self.traces.clear()
        self.logger.info("InMemory database disconnected and cleared")

    def health_check(self) -> bool:
        """In-memory health check always passes."""
        return True

    def fetch_unique_traces(self, limit: int) -> List[Dict[str, Any]]:
        """Return traces from memory, newest first."""
        with self.lock:
            if not self.traces:
                # Return sample traces for UI testing when empty
                return self._get_sample_traces()

            # Return up to 'limit' most recent traces
            traces_list = list(self.traces)
            # Reverse to get newest first
            traces_list.reverse()
            return traces_list[:limit]

    def get_trace_counts(self) -> Dict[str, int]:
        """Return trace counts from in-memory database."""
        with self.lock:
            if not self.traces:
                return {"total": 2, "errors": 1, "success": 1}  # Sample data counts

            total = len(self.traces)
            errors = len(
                [
                    t
                    for t in self.traces
                    if t.get("StatusCode", "").upper() not in ["OK", "STATUS_CODE_OK"]
                ]
            )
            return {"total": total, "errors": errors, "success": total - errors}

    def get_service_names(self) -> List[str]:
        """Return service names from in-memory database."""
        with self.lock:
            if not self.traces:
                return [
                    "api-gateway",
                    "auth-service",
                    "billing-service",
                    "order-service",
                    "notification-service",
                ]

            services = set()
            for trace in self.traces:
                if "ServiceName" in trace:
                    services.add(trace["ServiceName"])
            return sorted(list(services))

    def add_trace(self, trace: Dict[str, Any]) -> None:
        """Add a trace to the in-memory database."""
        with self.lock:
            # Add timestamp if not present
            if "Timestamp" not in trace:
                trace["Timestamp"] = datetime.now(timezone.utc)

            # Format the trace data for UI consistency
            self._format_trace_data(trace)

            # Add to memory (deque automatically handles max size)
            self.traces.append(trace)

            # Log the trace addition
            self.logger.debug(
                f"Added trace to in-memory store: {trace.get('TraceId', 'unknown')[:16]} "
                f"| Service: {trace.get('ServiceName', 'unknown')} "
                f"| Operation: {trace.get('SpanName', 'unknown')} "
                f"| Status: {trace.get('StatusCode', 'unknown')}"
            )

    def _get_sample_traces(self) -> List[Dict[str, Any]]:
        """Generate sample traces for UI testing when no real traces exist."""
        sample_traces = [
            {
                "TraceId": str(uuid.uuid4()),
                "SpanId": str(uuid.uuid4()),
                "ServiceName": "api-gateway",
                "SpanName": "GET /api/v1/users/1234",
                "StatusCode": "OK",
                "Timestamp": datetime.now(timezone.utc),
                "Duration": 15000000,  # 15ms in nanoseconds
                "SpanAttributes": {"http.method": "GET", "user.id": "1234"},
                "ResourceAttributes": {"service.name": "api-gateway"},
                "status_color": "positive",
            },
            {
                "TraceId": str(uuid.uuid4()),
                "SpanId": str(uuid.uuid4()),
                "ServiceName": "billing-service",
                "SpanName": "process_payment",
                "StatusCode": "Error",
                "StatusMessage": "Payment gateway timeout",
                "Timestamp": datetime.now(timezone.utc),
                "Duration": 5000000000,  # 5 seconds in nanoseconds
                "SpanAttributes": {"error.type": "PaymentGatewayTimeout"},
                "ResourceAttributes": {"service.name": "billing-service"},
                "status_color": "negative",
            },
        ]

        # Format each sample trace
        for trace in sample_traces:
            self._format_trace_data(trace)

        return sample_traces

    def _format_trace_data(self, trace_dict: Dict[str, Any]) -> None:
        """Format trace data for UI display."""
        # Format timestamp for display
        if "Timestamp" in trace_dict and trace_dict["Timestamp"]:
            try:
                if hasattr(trace_dict["Timestamp"], "strftime"):
                    trace_dict["formatted_timestamp"] = trace_dict[
                        "Timestamp"
                    ].strftime("%Y-%m-%d %H:%M:%S")
                    trace_dict["FormattedTime"] = trace_dict["Timestamp"].strftime(
                        "%H:%M:%S"
                    )
                else:
                    trace_dict["formatted_timestamp"] = str(trace_dict["Timestamp"])
                    trace_dict["FormattedTime"] = str(trace_dict["Timestamp"])
            except Exception:
                trace_dict["formatted_timestamp"] = "Invalid Date"
                trace_dict["FormattedTime"] = "Invalid"
        else:
            trace_dict["formatted_timestamp"] = "No Timestamp"
            trace_dict["FormattedTime"] = "N/A"

        # Format duration
        if "Duration" in trace_dict:
            duration_ns = int(trace_dict["Duration"]) if trace_dict["Duration"] else 0
            duration_ms = duration_ns / 1_000_000
            if duration_ms < 1:
                trace_dict["DurationMs"] = f"{duration_ms:.2f}ms"
            else:
                trace_dict["DurationMs"] = f"{duration_ms:.1f}ms"
        else:
            trace_dict["DurationMs"] = "N/A"

        # Short IDs for display
        trace_dict["ShortTraceId"] = str(trace_dict.get("TraceId", "unknown"))[:16]
        trace_dict["ShortSpanId"] = str(trace_dict.get("SpanId", "unknown"))[:16]

        # Determine status color
        status_code = trace_dict.get("StatusCode", "")
        if status_code is None:
            status_code = ""
        status_code = str(status_code).upper()
        if status_code in ["OK", "STATUS_CODE_OK"]:
            trace_dict["status_color"] = "positive"
        else:
            trace_dict["status_color"] = "negative"

        # Extract key info for display
        trace_dict["KeyInfo"] = self._extract_key_info(
            trace_dict.get("SpanAttributes", {})
        )

    def _extract_key_info(self, attrs: Dict[str, Any]) -> str:
        """Extract key information from span attributes for display."""
        if not attrs:
            return ""

        parts = []
        if attrs.get("error.type"):
            parts.append(f"🚨 {attrs['error.type']}")
        if not parts and attrs.get("user.id"):
            parts.append(f"👤 {attrs['user.id']}")
        if not parts and attrs.get("job.id"):
            parts.append(f"⚙️ {attrs['job.id']}")

        return " | ".join(parts)


# Factory function to create database instances
def create_database(db_type: str = None, **kwargs) -> DatabaseInterface:
    """Factory function to create database instances."""
    # Auto-detect database type if not specified
    if db_type is None:
        db_type = _auto_detect_database_type(**kwargs)

    # Check if we should use in-memory database
    if should_use_inmemory_database(db_type, **kwargs):
        max_traces = kwargs.get("max_traces") or int(
            os.getenv("INMEMORY_MAX_TRACES", "100")
        )
        return InMemoryDatabase(max_traces=max_traces)

    if db_type.lower() == "clickhouse":
        return ClickHouseDatabase(**kwargs)
    elif db_type.lower() in ["inmemory", "memory"]:
        max_traces = kwargs.get("max_traces") or int(
            os.getenv("INMEMORY_MAX_TRACES", "100")
        )
        return InMemoryDatabase(max_traces=max_traces)
    else:
        raise ValueError(
            f"Unsupported database type: {db_type}. Supported types: clickhouse, inmemory"
        )


def should_use_inmemory_database(db_type: str = None, **kwargs) -> bool:
    """Determine if we should use the in-memory database based on configuration."""
    logger = logging.getLogger(__name__)

    # Check if database type is explicitly set to in-memory
    if db_type and db_type.lower() in ["inmemory", "memory"]:
        logger.info("Using in-memory database (explicitly configured)")
        return True

    # Check if critical configuration is missing
    host = (
        kwargs.get("host", "")
        or os.getenv("DATABASE_HOST", "")
        or os.getenv("CLICKHOUSE_HOST", "")
    )
    if not host or host.strip() == "":
        logger.warning(
            "Database host not configured, falling back to in-memory database"
        )
        return True

    # Check if host is set to a placeholder value
    if host.lower() in ["none", "disabled", "mock", "false", "inmemory", "memory"]:
        logger.info(
            f"Database explicitly disabled (host='{host}'), using in-memory database"
        )
        return True

    return False


def _auto_detect_database_type(**kwargs) -> str:
    """Auto-detect database type from environment variables."""
    # Check explicit database type setting
    db_type = os.getenv("DATABASE_TYPE", "").lower()
    if db_type:
        return db_type

    # Check if ClickHouse configuration exists
    clickhouse_host = (
        kwargs.get("host") or os.getenv("DATABASE_HOST") or os.getenv("CLICKHOUSE_HOST")
    )
    if clickhouse_host and clickhouse_host.lower() not in [
        "none",
        "disabled",
        "mock",
        "false",
        "inmemory",
        "memory",
    ]:
        return "clickhouse"

    # Default to in-memory
    return "inmemory"


def get_database() -> DatabaseInterface:
    """
    Factory function to select the database backend based on env vars.
    Returns an instance of DatabaseInterface (ClickHouseDatabase or InMemoryDatabase).
    """
    logger = logging.getLogger(__name__)
    # Feature gate: Use localhost instead of 0.0.0.0 if enabled
    use_localhost = os.getenv("component.UseLocalHostAsDefaultHost", "").lower() in [
        "true",
        "1",
        "yes",
    ]
    db_type = os.getenv("DATABASE_TYPE", "").lower()
    host = os.getenv("DATABASE_HOST", "") or os.getenv("CLICKHOUSE_HOST", "")
    if use_localhost and host == "0.0.0.0":
        host = "localhost"
        logger.info(
            "Feature gate 'component.UseLocalHostAsDefaultHost' enabled, using localhost instead of 0.0.0.0"
        )
    port = int(os.getenv("DATABASE_PORT", os.getenv("CLICKHOUSE_PORT", "8123")))
    user = os.getenv("DATABASE_USER", "") or os.getenv("CLICKHOUSE_USER", "user")
    password = os.getenv("DATABASE_PASSWORD", "") or os.getenv(
        "CLICKHOUSE_PASSWORD", "password"
    )
    database = os.getenv("DATABASE_NAME", "") or os.getenv(
        "CLICKHOUSE_DATABASE", "otel"
    )
    try:
        db = create_database(
            db_type=db_type,
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
        logger.info(f"Database initialized: {type(db).__name__}")
        return db
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


# Define __all__ to explicitly export symbols - only exporting the classes and functions defined in this file
__all__ = [
    "DatabaseInterface",
    "ClickHouseDatabase",
    "InMemoryDatabase",
    "create_database",
    "get_database",
]
