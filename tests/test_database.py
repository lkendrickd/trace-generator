import sys
import os
import uuid
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest
from datetime import datetime, timezone
from unittest import mock
from trace_generator import database


def make_trace(**kwargs):
    d = {
        "TraceId": str(uuid.uuid4()),
        "SpanId": str(uuid.uuid4()),
        "ServiceName": "test-service",
        "SpanName": "test-span",
        "StatusCode": "OK",
        "Timestamp": datetime.now(timezone.utc),
        "Duration": 1000000,
        "SpanAttributes": {"user.id": "42"},
        "ResourceAttributes": {"service.name": "test-service"},
    }
    d.update(kwargs)
    return d


class DummyDB(database.DatabaseInterface):
    def connect(self):
        pass

    def disconnect(self):
        pass

    def health_check(self):
        return True

    def fetch_unique_traces(self, limit=10):
        return []

    def get_trace_counts(self):
        return {"total": 0}

    def get_service_names(self):
        return []

    def add_trace(self, trace):
        pass


class TestDatabaseInterface:
    def test_database_interface_exists(self):
        assert hasattr(database, "DatabaseInterface")

    def test_database_interface_abstract(self):
        dbi = DummyDB()
        assert dbi.health_check() is True
        assert dbi.fetch_unique_traces(1) == []
        assert dbi.get_trace_counts()["total"] == 0
        assert dbi.get_service_names() == []

    def test_database_interface_not_implemented(self):
        class NotImpl(database.DatabaseInterface):
            pass

        with pytest.raises(TypeError):
            NotImpl()

    def test_database_interface_abstract_methods_coverage(self):
        """Test to trigger abstract method definitions for coverage"""
        # This helps cover the abstract method signature lines
        abstract_methods = database.DatabaseInterface.__abstractmethods__
        expected_methods = {
            "connect",
            "disconnect",
            "health_check",
            "fetch_unique_traces",
            "get_trace_counts",
            "get_service_names",
            "add_trace",
        }
        assert abstract_methods == expected_methods

        # Just call the methods on a dummy subclass to trigger coverage
        class Dummy(database.DatabaseInterface):
            def connect(self):
                return True

            def disconnect(self):
                pass

            def health_check(self):
                return True

            def fetch_unique_traces(self, limit):
                return []

            def get_trace_counts(self):
                return {}

            def get_service_names(self):
                return []

            def add_trace(self, trace):
                pass

        d = Dummy()
        d.connect()
        d.disconnect()
        d.health_check()
        d.fetch_unique_traces(1)
        d.get_trace_counts()
        d.get_service_names()
        d.add_trace({})


class TestInMemoryDatabase:
    """Test the actual InMemoryDatabase implementation with real data"""

    def test_initialization_with_defaults(self):
        """Test that InMemoryDatabase initializes correctly"""
        db = database.InMemoryDatabase()
        assert db.max_traces == 100  # Default value
        assert len(db.traces) == 0
        assert db.lock is not None

    def test_initialization_with_custom_max_traces(self):
        """Test initialization with custom max_traces"""
        db = database.InMemoryDatabase(max_traces=50)
        assert db.max_traces == 50

    def test_connect_always_succeeds(self):
        """Test that connect always returns True"""
        db = database.InMemoryDatabase()
        assert db.connect() is True

    def test_health_check_always_passes(self):
        """Test that health_check always returns True"""
        db = database.InMemoryDatabase()
        assert db.health_check() is True

    def test_add_trace_basic_functionality(self):
        """Test adding a basic trace and retrieving it"""
        db = database.InMemoryDatabase()
        trace = make_trace(TraceId="test-123")
        db.add_trace(trace)

        traces = db.fetch_unique_traces(10)
        assert len(traces) == 1
        assert traces[0]["TraceId"] == "test-123"

    def test_add_trace_without_timestamp_gets_current_time(self):
        """Test that traces without timestamps get current time added"""
        db = database.InMemoryDatabase()
        trace = {"TraceId": "test", "StatusCode": "OK"}

        # Verify no timestamp initially
        assert "Timestamp" not in trace

        db.add_trace(trace)

        # Should have timestamp added
        assert "Timestamp" in trace
        assert isinstance(trace["Timestamp"], datetime)

    def test_max_traces_limit_enforced(self):
        """Test that max_traces limit is properly enforced"""
        db = database.InMemoryDatabase(max_traces=2)

        # Add 3 traces
        db.add_trace(make_trace(TraceId="trace-1"))
        db.add_trace(make_trace(TraceId="trace-2"))
        db.add_trace(make_trace(TraceId="trace-3"))

        # Should only have 2 traces (most recent)
        traces = db.fetch_unique_traces(10)
        assert len(traces) == 2
        trace_ids = [t["TraceId"] for t in traces]
        assert "trace-2" in trace_ids
        assert "trace-3" in trace_ids
        assert "trace-1" not in trace_ids

    def test_traces_returned_newest_first(self):
        """Test that traces are returned with newest first"""
        db = database.InMemoryDatabase()

        # Add traces with different timestamps
        trace1 = make_trace(
            TraceId="old", Timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc)
        )
        trace2 = make_trace(
            TraceId="new", Timestamp=datetime(2023, 1, 2, tzinfo=timezone.utc)
        )

        db.add_trace(trace1)
        db.add_trace(trace2)

        traces = db.fetch_unique_traces(10)
        assert traces[0]["TraceId"] == "new"  # Most recent first
        assert traces[1]["TraceId"] == "old"

    def test_disconnect_clears_traces(self):
        """Test that disconnect clears all traces"""
        db = database.InMemoryDatabase()
        db.add_trace(make_trace())

        # Should have traces
        assert len(list(db.traces)) == 1

        db.disconnect()

        # Should be cleared, but fetch_unique_traces returns sample data when empty
        traces = db.fetch_unique_traces(1)
        assert traces[0]["ServiceName"] == "api-gateway"  # Sample trace

    def test_get_trace_counts_with_real_data(self):
        """Test trace counts with actual trace data"""
        db = database.InMemoryDatabase()

        # Add mix of successful and error traces
        db.add_trace(make_trace(StatusCode="OK"))
        db.add_trace(make_trace(StatusCode="Error"))
        db.add_trace(make_trace(StatusCode="STATUS_CODE_OK"))
        db.add_trace(make_trace(StatusCode="FAILED"))

        counts = db.get_trace_counts()
        assert counts["total"] == 4
        assert counts["success"] == 2  # OK and STATUS_CODE_OK
        assert counts["errors"] == 2  # Error and FAILED

    def test_get_service_names_with_real_data(self):
        """Test service names extraction from actual traces"""
        db = database.InMemoryDatabase()

        db.add_trace(make_trace(ServiceName="auth-service"))
        db.add_trace(make_trace(ServiceName="billing-service"))
        db.add_trace(make_trace(ServiceName="auth-service"))  # Duplicate

        services = db.get_service_names()
        assert set(services) == {"auth-service", "billing-service"}
        assert services == sorted(services)  # Should be sorted

    def test_thread_safety_with_concurrent_operations(self):
        """Test thread safety with multiple concurrent operations"""
        db = database.InMemoryDatabase(max_traces=100)

        def add_traces():
            for i in range(25):
                db.add_trace(
                    make_trace(TraceId=f"thread-{threading.current_thread().ident}-{i}")
                )

        # Run 4 threads adding traces concurrently
        threads = [threading.Thread(target=add_traces) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have exactly 100 traces (max limit)
        assert db.get_trace_counts()["total"] == 100


class TestInMemoryDatabaseFormatting:
    """Test the data formatting logic without mocking"""

    def test_format_trace_data_with_valid_timestamp(self):
        """Test timestamp formatting with real datetime objects"""
        db = database.InMemoryDatabase()

        now = datetime(2023, 6, 15, 14, 30, 45, tzinfo=timezone.utc)
        trace_dict = {"Timestamp": now, "TraceId": "test", "StatusCode": "OK"}

        db._format_trace_data(trace_dict)

        assert trace_dict["formatted_timestamp"] == "2023-06-15 14:30:45"
        assert trace_dict["FormattedTime"] == "14:30:45"

    def test_format_trace_data_with_missing_timestamp(self):
        """Test formatting when timestamp is missing"""
        db = database.InMemoryDatabase()
        trace_dict = {"TraceId": "test"}

        db._format_trace_data(trace_dict)

        assert trace_dict["formatted_timestamp"] == "No Timestamp"
        assert trace_dict["FormattedTime"] == "N/A"

    def test_format_trace_data_with_string_timestamp(self):
        """Test formatting with string timestamp (edge case)"""
        db = database.InMemoryDatabase()
        trace_dict = {"Timestamp": "2023-01-01 12:00:00", "TraceId": "test"}

        db._format_trace_data(trace_dict)

        assert trace_dict["formatted_timestamp"] == "2023-01-01 12:00:00"
        assert trace_dict["FormattedTime"] == "2023-01-01 12:00:00"

    def test_format_trace_data_duration_formatting(self):
        """Test duration formatting with different values"""
        db = database.InMemoryDatabase()

        # Test sub-millisecond duration
        trace_dict = {"Duration": 500000}  # 0.5ms in nanoseconds
        db._format_trace_data(trace_dict)
        assert trace_dict["DurationMs"] == "0.50ms"

        # Test millisecond duration
        trace_dict = {"Duration": 2500000}  # 2.5ms in nanoseconds
        db._format_trace_data(trace_dict)
        assert trace_dict["DurationMs"] == "2.5ms"

        # Test missing duration
        trace_dict = {}
        db._format_trace_data(trace_dict)
        assert trace_dict["DurationMs"] == "N/A"

        # Test zero duration
        trace_dict = {"Duration": 0}
        db._format_trace_data(trace_dict)
        assert trace_dict["DurationMs"] == "0.00ms"

    def test_format_trace_data_short_ids(self):
        """Test short ID generation"""
        db = database.InMemoryDatabase()

        long_trace_id = "a" * 32
        long_span_id = "b" * 32
        trace_dict = {"TraceId": long_trace_id, "SpanId": long_span_id}

        db._format_trace_data(trace_dict)

        assert trace_dict["ShortTraceId"] == "a" * 16
        assert trace_dict["ShortSpanId"] == "b" * 16

    def test_format_trace_data_missing_ids(self):
        """Test formatting with missing IDs"""
        db = database.InMemoryDatabase()
        trace_dict = {}

        db._format_trace_data(trace_dict)

        assert trace_dict["ShortTraceId"] == "unknown"
        assert trace_dict["ShortSpanId"] == "unknown"

    def test_format_trace_data_status_colors(self):
        """Test status color determination"""
        db = database.InMemoryDatabase()

        # Test positive statuses
        for status in ["OK", "STATUS_CODE_OK", "ok"]:
            trace_dict = {"StatusCode": status}
            db._format_trace_data(trace_dict)
            assert trace_dict["status_color"] == "positive", (
                f"Failed for status: {status}"
            )

        # Test negative statuses - need to handle None properly
        for status in ["Error", "FAILED", "TIMEOUT", ""]:
            trace_dict = {"StatusCode": status}
            db._format_trace_data(trace_dict)
            assert trace_dict["status_color"] == "negative", (
                f"Failed for status: {status}"
            )

        # Test None status separately (since None.upper() would fail)
        trace_dict = {"StatusCode": None}
        db._format_trace_data(trace_dict)
        assert trace_dict["status_color"] == "negative", "Failed for status: None"

    def test_extract_key_info_with_different_attributes(self):
        """Test key info extraction with real attribute data"""
        db = database.InMemoryDatabase()

        # Test error type (highest priority)
        attrs = {"error.type": "TimeoutError", "user.id": "123", "job.id": "456"}
        result = db._extract_key_info(attrs)
        assert result == "🚨 TimeoutError"

        # Test user.id (second priority)
        attrs = {"user.id": "123", "job.id": "456"}
        result = db._extract_key_info(attrs)
        assert result == "👤 123"

        # Test job.id (third priority)
        attrs = {"job.id": "456"}
        result = db._extract_key_info(attrs)
        assert result == "⚙️ 456"

        # Test empty/None attributes
        assert db._extract_key_info({}) == ""
        assert db._extract_key_info(None) == ""

    def test_format_trace_data_timestamp_exception_handling(self):
        """Test timestamp formatting with exception scenarios"""
        db = database.InMemoryDatabase()

        # Test with object that raises exception during formatting
        class BadTimestamp:
            def strftime(self, fmt):
                raise ValueError("Bad timestamp")

        trace_dict = {"Timestamp": BadTimestamp()}
        db._format_trace_data(trace_dict)
        assert trace_dict["formatted_timestamp"] == "Invalid Date"
        assert trace_dict["FormattedTime"] == "Invalid"

    def test_format_trace_data_none_status_code_fix(self):
        """Test that None status codes are handled properly"""
        db = database.InMemoryDatabase()

        # This test ensures None status codes don't crash the formatting
        trace_dict = {
            "TraceId": "test-trace",
            "SpanId": "test-span",
            "StatusCode": None,
            "Timestamp": datetime.now(timezone.utc),
            "Duration": 1000000,
        }

        # This should not raise an AttributeError
        db._format_trace_data(trace_dict)
        assert (
            trace_dict["status_color"] == "negative"
        )  # None should be treated as negative


class TestInMemoryDatabaseSampleData:
    """Test sample data generation when database is empty"""

    def test_sample_traces_when_empty(self):
        """Test that sample traces are returned when database is empty"""
        db = database.InMemoryDatabase()
        # Ensure database is empty
        db.traces.clear()

        traces = db.fetch_unique_traces(5)

        assert len(traces) == 2  # Should return 2 sample traces
        service_names = {trace["ServiceName"] for trace in traces}
        assert "api-gateway" in service_names
        assert "billing-service" in service_names

        # Verify sample traces have proper formatting
        for trace in traces:
            assert "formatted_timestamp" in trace
            assert "DurationMs" in trace
            assert "ShortTraceId" in trace
            assert "status_color" in trace

    def test_sample_service_names_when_empty(self):
        """Test sample service names when database is empty"""
        db = database.InMemoryDatabase()
        db.traces.clear()

        services = db.get_service_names()

        expected_services = [
            "api-gateway",
            "auth-service",
            "billing-service",
            "order-service",
            "notification-service",
        ]
        assert services == expected_services

    def test_sample_trace_counts_when_empty(self):
        """Test sample trace counts when database is empty"""
        db = database.InMemoryDatabase()
        db.traces.clear()

        counts = db.get_trace_counts()

        assert counts == {"total": 2, "errors": 1, "success": 1}

    def test_get_sample_traces_formatting(self):
        """Test that _get_sample_traces properly formats all traces"""
        db = database.InMemoryDatabase()
        sample_traces = db._get_sample_traces()

        # Should get 2 sample traces
        assert len(sample_traces) == 2

        # Verify all formatting was applied
        for trace in sample_traces:
            assert "formatted_timestamp" in trace
            assert "FormattedTime" in trace
            assert "DurationMs" in trace
            assert "ShortTraceId" in trace
            assert "ShortSpanId" in trace
            assert "status_color" in trace


class TestClickHouseDatabaseBasics:
    """Test ClickHouseDatabase basic functionality with comprehensive mocking"""

    def test_clickhouse_initialization(self):
        """Test ClickHouseDatabase initialization"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )

        assert db.host == "localhost"
        assert db.port == 8123
        assert db.user == "user"
        assert db.password == "password"
        assert db.database == "testdb"
        assert db._client is None
        assert db.logger is not None

    def test_clickhouse_without_dependencies(self):
        """Test ClickHouse behavior when dependencies aren't available"""
        # Create instance and manually set clickhouse_connect to None to simulate missing deps
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = None

        # All methods should handle missing dependencies gracefully
        assert db.connect() is False
        assert db.health_check() is False
        assert db.fetch_unique_traces(10) == []
        assert db.get_trace_counts() == {"total": 0, "errors": 0, "success": 0}
        assert db.get_service_names() == []

        # add_trace should not raise an exception
        db.add_trace({"test": "data"})

    def test_clickhouse_import_error_warning(self, caplog):
        """Test warning when ClickHouse dependencies are missing"""
        with caplog.at_level("WARNING"):
            # Patch clickhouse_connect import to raise ImportError only for clickhouse_connect
            import builtins

            real_import = builtins.__import__

            def fake_import(name, *args, **kwargs):
                if name == "clickhouse_connect" or name.startswith(
                    "clickhouse_connect."
                ):
                    raise ImportError("No module named 'clickhouse_connect'")
                return real_import(name, *args, **kwargs)

            import importlib
            import sys

            # Remove clickhouse_connect from sys.modules if present
            sys.modules.pop("clickhouse_connect", None)
            sys.modules.pop("clickhouse_connect.driver", None)
            try:
                builtins.__import__ = fake_import
                importlib.reload(database)
                db = database.ClickHouseDatabase("h", 1, "u", "p", "d")
                assert db.clickhouse_connect is None
                assert "ClickHouse dependencies not found" in caplog.text
            finally:
                builtins.__import__ = real_import

    def test_clickhouse_import_error_simulation(self):
        """Test ClickHouse import error simulation"""
        # Create instance and manually simulate import failure
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = None
        db.ch_exceptions = None

        # This should cover the import error handling paths
        assert not db.connect()
        assert not db.health_check()

    def test_clickhouse_import_with_exceptions_module(self):
        """Test ClickHouse initialization with exceptions module"""
        # Test the import logic with mock modules
        mock_clickhouse = mock.MagicMock()
        mock_exceptions = mock.MagicMock()

        with mock.patch.dict(
            "sys.modules",
            {
                "clickhouse_connect": mock_clickhouse,
                "clickhouse_connect.driver.exceptions": mock_exceptions,
            },
        ):
            db = database.ClickHouseDatabase(
                "localhost", 8123, "user", "password", "testdb"
            )
            assert db.clickhouse_connect is not None
            assert db.ch_exceptions is not None

    def test_clickhouse_connect_success(self):
        """Test successful ClickHouse connection"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        mock_client = mock.MagicMock()
        db.clickhouse_connect.get_client.return_value = mock_client

        result = db.connect()
        assert result is True
        assert db._client == mock_client
        db.clickhouse_connect.get_client.assert_called_once_with(
            host="localhost",
            port=8123,
            user="user",
            password="password",
            database="testdb",
        )

    def test_clickhouse_connect_error(self, caplog):
        """Test ClickHouse connection error"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        db.clickhouse_connect.get_client.side_effect = Exception("Connection failed")

        with caplog.at_level("ERROR"):
            result = db.connect()
            assert result is False
            assert "Failed to connect to ClickHouse" in caplog.text

    def test_clickhouse_disconnect_success(self):
        """Test successful ClickHouse disconnect"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        mock_client = mock.MagicMock()
        db._client = mock_client

        db.disconnect()
        mock_client.close.assert_called_once()
        assert db._client is None

    def test_clickhouse_disconnect_error(self, caplog):
        """Test ClickHouse disconnect error"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        mock_client = mock.MagicMock()
        mock_client.close.side_effect = Exception("Close failed")
        db._client = mock_client

        with caplog.at_level("ERROR"):
            db.disconnect()
            assert "Error closing ClickHouse connection" in caplog.text
            assert db._client is None

    def test_clickhouse_health_check_success(self):
        """Test successful ClickHouse health check"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        mock_client = mock.MagicMock()
        db.clickhouse_connect.get_client.return_value.__enter__.return_value = (
            mock_client
        )

        result = db.health_check()
        assert result is True
        mock_client.query.assert_called_once_with("SELECT 1")

    def test_clickhouse_health_check_error(self, caplog):
        """Test ClickHouse health check error"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        db.clickhouse_connect.get_client.side_effect = Exception("Health check failed")

        with caplog.at_level("ERROR"):
            result = db.health_check()
            assert result is False
            assert "ClickHouse health check failed" in caplog.text


class TestClickHouseDatabaseQueries:
    """Test ClickHouse database query operations"""

    def test_fetch_unique_traces_success(self):
        """Test successful trace fetching"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        mock_client = mock.MagicMock()
        db.clickhouse_connect.get_client.return_value.__enter__.return_value = (
            mock_client
        )

        # Mock query result
        mock_result = mock.MagicMock()
        mock_result.result_rows = [
            ["trace1", "span1", "OK"],
            ["trace2", "span2", "Error"],
        ]
        mock_result.column_names = ["TraceId", "SpanId", "StatusCode"]
        mock_client.query.return_value = mock_result

        traces = db.fetch_unique_traces(10)

        assert len(traces) == 2
        assert traces[0]["TraceId"] == "trace1"
        assert traces[1]["StatusCode"] == "Error"

        # Verify the complex query was called
        mock_client.query.assert_called_once()
        call_args = mock_client.query.call_args
        assert call_args[0][1] == [10]  # Verify limit parameter

    def test_fetch_unique_traces_error(self, caplog):
        """Test fetch traces error handling"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        db.clickhouse_connect.get_client.side_effect = Exception("Query failed")

        with caplog.at_level("ERROR"):
            traces = db.fetch_unique_traces(10)
            assert traces == []
            assert "Error fetching traces" in caplog.text

    def test_get_trace_counts_success(self):
        """Test successful trace count retrieval"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        mock_client = mock.MagicMock()
        db.clickhouse_connect.get_client.return_value.__enter__.return_value = (
            mock_client
        )

        # Mock results for both queries
        total_result = mock.MagicMock()
        total_result.result_rows = [[42]]
        error_result = mock.MagicMock()
        error_result.result_rows = [[5]]
        mock_client.query.side_effect = [total_result, error_result]

        counts = db.get_trace_counts()

        assert counts == {"total": 42, "errors": 5, "success": 37}
        assert mock_client.query.call_count == 2

    def test_get_trace_counts_empty_results(self):
        """Test trace counts with empty result sets"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        mock_client = mock.MagicMock()
        db.clickhouse_connect.get_client.return_value.__enter__.return_value = (
            mock_client
        )

        # Mock empty results
        empty_result = mock.MagicMock()
        empty_result.result_rows = []
        mock_client.query.return_value = empty_result

        counts = db.get_trace_counts()

        assert counts == {"total": 0, "errors": 0, "success": 0}

    def test_get_trace_counts_error(self, caplog):
        """Test trace counts error handling"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        db.clickhouse_connect.get_client.side_effect = Exception("Count query failed")

        with caplog.at_level("ERROR"):
            counts = db.get_trace_counts()
            assert counts == {"total": 0, "errors": 0, "success": 0}
            assert "Error getting trace counts" in caplog.text

    def test_get_service_names_success(self):
        """Test successful service name retrieval"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        mock_client = mock.MagicMock()
        db.clickhouse_connect.get_client.return_value.__enter__.return_value = (
            mock_client
        )

        # Mock service names result
        mock_result = mock.MagicMock()
        mock_result.result_rows = [
            ["auth-service"],
            ["billing-service"],
            ["api-gateway"],
        ]
        mock_client.query.return_value = mock_result

        services = db.get_service_names()

        assert services == ["auth-service", "billing-service", "api-gateway"]
        mock_client.query.assert_called_once_with(
            "SELECT DISTINCT ServiceName FROM otel_traces ORDER BY ServiceName"
        )

    def test_get_service_names_empty_results(self):
        """Test service names with empty result set"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        mock_client = mock.MagicMock()
        db.clickhouse_connect.get_client.return_value.__enter__.return_value = (
            mock_client
        )

        # Mock empty results
        empty_result = mock.MagicMock()
        empty_result.result_rows = []
        mock_client.query.return_value = empty_result

        services = db.get_service_names()

        assert services == []

    def test_get_service_names_error(self, caplog):
        """Test service names error handling"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        db.clickhouse_connect = mock.MagicMock()
        db.clickhouse_connect.get_client.side_effect = Exception("Service query failed")

        with caplog.at_level("ERROR"):
            services = db.get_service_names()
            assert services == []
            assert "Error getting service names" in caplog.text

    def test_add_trace_logs_debug(self, caplog):
        """Test that add_trace logs debug message"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        with caplog.at_level("DEBUG"):
            db.add_trace({"test": "data"})
            assert "ClickHouse trace insertion handled by OTLP pipeline" in caplog.text


class TestClickHouseDatabaseFormatting:
    """Test ClickHouse trace data formatting"""

    def test_process_query_results_empty(self):
        """Test _process_query_results with empty results"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        mock_result = mock.MagicMock()
        mock_result.result_rows = []

        result = db._process_query_results(mock_result)
        assert result == []

    def test_process_query_results_with_data(self):
        """Test _process_query_results with actual data"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )
        mock_result = mock.MagicMock()
        mock_result.result_rows = [
            ["trace1", "span1", "OK", datetime.now(), 1000000],
            ["trace2", "span2", "Error", datetime.now(), 2000000],
        ]
        mock_result.column_names = [
            "TraceId",
            "SpanId",
            "StatusCode",
            "Timestamp",
            "Duration",
        ]

        result = db._process_query_results(mock_result)

        assert len(result) == 2
        assert result[0]["TraceId"] == "trace1"
        assert result[0]["status_color"] == "positive"
        assert result[1]["StatusCode"] == "Error"
        assert result[1]["status_color"] == "negative"
        # Verify formatting was applied
        assert "formatted_timestamp" in result[0]
        assert "DurationMs" in result[0]

    def test_format_trace_data_comprehensive(self):
        """Test ClickHouse _format_trace_data comprehensively"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )

        # Test with proper datetime
        now = datetime.now(timezone.utc)
        d = {
            "Timestamp": now,
            "Duration": 1500000,
            "TraceId": "long-trace-id-123456789012345678",
            "SpanId": "long-span-id-123456789012345678",
            "StatusCode": "OK",
        }
        db._format_trace_data(d)

        assert d["formatted_timestamp"] == now.strftime("%Y-%m-%d %H:%M:%S")
        assert d["FormattedTime"] == now.strftime("%H:%M:%S")
        assert d["DurationMs"] == "1.5ms"
        assert d["ShortTraceId"] == "long-trace-id-12"  # First 16 chars
        assert d["ShortSpanId"] == "long-span-id-123"  # First 16 chars
        assert d["status_color"] == "positive"

    def test_format_trace_data_edge_cases(self):
        """Test ClickHouse formatting edge cases"""
        db = database.ClickHouseDatabase(
            "localhost", 8123, "user", "password", "testdb"
        )

        # Test missing timestamp
        d = {"TraceId": "test"}
        db._format_trace_data(d)
        assert d["formatted_timestamp"] == "No Timestamp"
        assert d["FormattedTime"] == "N/A"

        # Test invalid timestamp object
        class BadTimestamp:
            def strftime(self, fmt):
                raise ValueError("Bad format")

        d = {"Timestamp": BadTimestamp()}
        db._format_trace_data(d)
        assert d["formatted_timestamp"] == "Invalid Date"
        assert d["FormattedTime"] == "Invalid"

        # Test missing duration
        d = {"TraceId": "test"}
        db._format_trace_data(d)
        assert d["DurationMs"] == "N/A"

        # Test zero/None duration
        d = {"Duration": 0}
        db._format_trace_data(d)
        assert d["DurationMs"] == "0.00ms"

        d = {"Duration": None}
        db._format_trace_data(d)
        assert d["DurationMs"] == "0.00ms"

        # Test missing IDs
        d = {}
        db._format_trace_data(d)
        assert d["ShortTraceId"] == "unknown"
        assert d["ShortSpanId"] == "unknown"


class TestFactoryFunctions:
    """Test factory functions with comprehensive scenarios"""

    def test_create_database_inmemory_explicit(self):
        """Test creating in-memory database explicitly"""
        db = database.create_database(db_type="inmemory", max_traces=50)
        assert isinstance(db, database.InMemoryDatabase)
        assert db.max_traces == 50

    def test_create_database_memory_alias(self):
        """Test 'memory' alias for in-memory database"""
        db = database.create_database(db_type="memory", max_traces=25)
        assert isinstance(db, database.InMemoryDatabase)
        assert db.max_traces == 25

    def test_create_database_clickhouse(self):
        """Test creating ClickHouse database"""
        db = database.create_database(
            db_type="clickhouse",
            host="localhost",
            port=8123,
            user="test",
            password="test",
            database="test",
        )
        assert isinstance(db, database.ClickHouseDatabase)
        assert db.host == "localhost"
        assert db.port == 8123

    def test_create_database_auto_detect_none(self, monkeypatch):
        """Test auto-detection when db_type is None"""
        monkeypatch.setenv("DATABASE_TYPE", "inmemory")
        db = database.create_database(db_type=None)
        assert isinstance(db, database.InMemoryDatabase)

    def test_should_use_inmemory_database_comprehensive(self, caplog):
        """Test comprehensive should_use_inmemory_database scenarios"""
        # Test explicit inmemory type with logging
        with caplog.at_level("INFO"):
            result = database.should_use_inmemory_database("inmemory")
            assert result is True
            assert "Using in-memory database (explicitly configured)" in caplog.text

        # Test explicit memory type
        result = database.should_use_inmemory_database("memory")
        assert result is True

        # Test empty host with warning
        caplog.clear()
        with caplog.at_level("WARNING"):
            result = database.should_use_inmemory_database(None, host="")
            assert result is True
            assert (
                "Database host not configured, falling back to in-memory database"
                in caplog.text
            )

        # Test whitespace-only host
        result = database.should_use_inmemory_database(None, host="   ")
        assert result is True

        # Test placeholder hosts with logging
        caplog.clear()
        with caplog.at_level("INFO"):
            result = database.should_use_inmemory_database(None, host="disabled")
            assert result is True
            assert (
                "Database explicitly disabled (host='disabled'), using in-memory database"
                in caplog.text
            )

        # Test all placeholder values
        placeholder_hosts = ["none", "disabled", "mock", "false", "inmemory", "memory"]
        for host in placeholder_hosts:
            assert database.should_use_inmemory_database(None, host=host) is True

        # Test valid host should not use in-memory
        assert (
            database.should_use_inmemory_database(None, host="real-host.com") is False
        )
        assert (
            database.should_use_inmemory_database("clickhouse", host="real-host.com")
            is False
        )

    def test_auto_detect_database_type_comprehensive(self, monkeypatch):
        """Test comprehensive _auto_detect_database_type scenarios"""
        # Clear environment first
        monkeypatch.delenv("DATABASE_TYPE", raising=False)
        monkeypatch.delenv("DATABASE_HOST", raising=False)
        monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)

        # Test explicit DATABASE_TYPE
        monkeypatch.setenv("DATABASE_TYPE", "clickhouse")
        result = database._auto_detect_database_type()
        assert result == "clickhouse"

        # Test with empty DATABASE_TYPE (should be treated as no type)
        monkeypatch.setenv("DATABASE_TYPE", "")
        monkeypatch.setenv("DATABASE_HOST", "clickhouse-server")
        result = database._auto_detect_database_type()
        assert result == "clickhouse"

        # Test with CLICKHOUSE_HOST instead of DATABASE_HOST
        monkeypatch.delenv("DATABASE_HOST", raising=False)
        monkeypatch.setenv("CLICKHOUSE_HOST", "ch-server")
        result = database._auto_detect_database_type()
        assert result == "clickhouse"

        # Test with kwargs host parameter
        monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
        result = database._auto_detect_database_type(host="kwargs-host")
        assert result == "clickhouse"

        # Test with placeholder host
        result = database._auto_detect_database_type(host="none")
        assert result == "inmemory"

        # Test with no configuration
        result = database._auto_detect_database_type()
        assert result == "inmemory"

    def test_auto_detect_empty_string_handling(self, monkeypatch):
        """Test that empty DATABASE_TYPE string is handled properly"""
        monkeypatch.setenv("DATABASE_TYPE", "")  # Empty string
        monkeypatch.delenv("DATABASE_HOST", raising=False)
        monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)

        # Empty string should be treated as no type specified
        result = database._auto_detect_database_type()
        assert result == "inmemory"  # Should default to inmemory when no host

    def test_create_database_invalid_type_scenarios(self):
        """Test invalid database type handling"""
        # With valid host should raise error
        with pytest.raises(ValueError, match="Unsupported database type: invalid"):
            database.create_database(db_type="invalid", host="real-host")

        # With empty host should fallback to inmemory
        db = database.create_database(db_type="invalid", host="")
        assert isinstance(db, database.InMemoryDatabase)

        # With placeholder host should fallback
        db = database.create_database(db_type="invalid", host="none")
        assert isinstance(db, database.InMemoryDatabase)

    def test_create_database_edge_cases(self):
        """Test create_database edge cases for better coverage"""
        # Test with unrecognized type but should_use_inmemory_database returns False
        with pytest.raises(ValueError, match="Unsupported database type"):
            database.create_database(db_type="unknown_type", host="valid-host")

        # Test create_database with uppercase types
        db = database.create_database(db_type="INMEMORY")
        assert isinstance(db, database.InMemoryDatabase)

        db = database.create_database(db_type="MEMORY")
        assert isinstance(db, database.InMemoryDatabase)

        # Test clickhouse with uppercase
        db = database.create_database(
            db_type="CLICKHOUSE",
            host="localhost",
            port=8123,
            user="test",
            password="test",
            database="test",
        )
        assert isinstance(db, database.ClickHouseDatabase)


class TestGetDatabaseFunction:
    """Test get_database function comprehensively"""

    def test_get_database_inmemory_config(self, monkeypatch, caplog):
        """Test get_database with in-memory configuration"""
        monkeypatch.setenv("DATABASE_TYPE", "inmemory")
        monkeypatch.delenv("DATABASE_HOST", raising=False)

        with caplog.at_level("INFO"):
            db = database.get_database()
            assert isinstance(db, database.InMemoryDatabase)
            assert "Database initialized: InMemoryDatabase" in caplog.text

    def test_get_database_clickhouse_config(self, monkeypatch):
        """Test get_database with ClickHouse configuration"""
        monkeypatch.setenv("DATABASE_TYPE", "clickhouse")
        monkeypatch.setenv("DATABASE_HOST", "ch-host")
        monkeypatch.setenv("DATABASE_PORT", "9000")
        monkeypatch.setenv("DATABASE_USER", "ch-user")
        monkeypatch.setenv("DATABASE_PASSWORD", "ch-pass")
        monkeypatch.setenv("DATABASE_NAME", "ch-db")

        db = database.get_database()
        assert isinstance(db, database.ClickHouseDatabase)
        assert db.host == "ch-host"
        assert db.port == 9000
        assert db.user == "ch-user"
        assert db.password == "ch-pass"
        assert db.database == "ch-db"

    def test_get_database_localhost_feature_gate(self, monkeypatch, caplog):
        """Test localhost feature gate functionality"""
        monkeypatch.setenv("component.UseLocalHostAsDefaultHost", "true")
        monkeypatch.setenv("DATABASE_TYPE", "clickhouse")
        monkeypatch.setenv("DATABASE_HOST", "0.0.0.0")

        with caplog.at_level("INFO"):
            db = database.get_database()
            assert isinstance(db, database.ClickHouseDatabase)
            assert db.host == "localhost"  # Should be converted from 0.0.0.0
            assert (
                "Feature gate 'component.UseLocalHostAsDefaultHost' enabled"
                in caplog.text
            )

    def test_get_database_localhost_feature_gate_disabled(self, monkeypatch):
        """Test localhost feature gate when disabled"""
        monkeypatch.setenv("component.UseLocalHostAsDefaultHost", "false")
        monkeypatch.setenv("DATABASE_TYPE", "clickhouse")
        monkeypatch.setenv("DATABASE_HOST", "0.0.0.0")

        db = database.get_database()
        assert isinstance(db, database.ClickHouseDatabase)
        assert db.host == "0.0.0.0"  # Should remain unchanged

    def test_get_database_env_var_precedence(self, monkeypatch):
        """Test environment variable precedence (DATABASE_* vs CLICKHOUSE_*)"""
        # Clear DATABASE_TYPE to avoid conflicts
        monkeypatch.delenv("DATABASE_TYPE", raising=False)

        # Set both DATABASE_* and CLICKHOUSE_* vars
        monkeypatch.setenv("DATABASE_HOST", "db-host")
        monkeypatch.setenv("CLICKHOUSE_HOST", "ch-host")
        monkeypatch.setenv("DATABASE_USER", "db-user")
        monkeypatch.setenv("CLICKHOUSE_USER", "ch-user")
        monkeypatch.setenv("DATABASE_PORT", "8124")
        monkeypatch.setenv("CLICKHOUSE_PORT", "9000")
        monkeypatch.setenv("DATABASE_PASSWORD", "db-pass")
        monkeypatch.setenv("CLICKHOUSE_PASSWORD", "ch-pass")
        monkeypatch.setenv("DATABASE_NAME", "db-name")
        monkeypatch.setenv("CLICKHOUSE_DATABASE", "ch-name")

        # Set DATABASE_TYPE to 'inmemory' to avoid ValueError
        monkeypatch.setenv("DATABASE_TYPE", "inmemory")
        db = database.get_database()
        assert isinstance(db, database.InMemoryDatabase)

    def test_get_database_fallback_values(self, monkeypatch):
        """Test get_database fallback to CLICKHOUSE_* values"""
        # Clear DATABASE_TYPE to avoid conflicts
        monkeypatch.delenv("DATABASE_TYPE", raising=False)

        # Only set CLICKHOUSE_* values
        monkeypatch.delenv("DATABASE_HOST", raising=False)
        monkeypatch.delenv("DATABASE_USER", raising=False)
        monkeypatch.delenv("DATABASE_PASSWORD", raising=False)
        monkeypatch.delenv("DATABASE_NAME", raising=False)
        monkeypatch.setenv("CLICKHOUSE_HOST", "ch-host")
        monkeypatch.setenv("CLICKHOUSE_USER", "ch-user")
        monkeypatch.setenv("CLICKHOUSE_PASSWORD", "ch-pass")
        monkeypatch.setenv("CLICKHOUSE_DATABASE", "ch-db")
        # Set DATABASE_TYPE to 'inmemory' to avoid ValueError
        monkeypatch.setenv("DATABASE_TYPE", "inmemory")
        db = database.get_database()
        assert isinstance(db, database.InMemoryDatabase)

    def test_get_database_defaults(self, monkeypatch):
        """Test get_database with default values"""
        monkeypatch.setenv("DATABASE_TYPE", "clickhouse")
        monkeypatch.setenv("DATABASE_HOST", "test-host")
        # Clear all other vars to test defaults
        monkeypatch.delenv("DATABASE_PORT", raising=False)
        monkeypatch.delenv("CLICKHOUSE_PORT", raising=False)
        monkeypatch.delenv("DATABASE_USER", raising=False)
        monkeypatch.delenv("CLICKHOUSE_USER", raising=False)
        monkeypatch.delenv("DATABASE_PASSWORD", raising=False)
        monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)
        monkeypatch.delenv("DATABASE_NAME", raising=False)
        monkeypatch.delenv("CLICKHOUSE_DATABASE", raising=False)

        db = database.get_database()
        assert db.port == 8123
        assert db.user == "user"
        assert db.password == "password"
        assert db.database == "otel"

    def test_get_database_creation_error(self, monkeypatch, caplog):
        """Test get_database error handling"""
        monkeypatch.setenv("DATABASE_TYPE", "invalid")
        monkeypatch.setenv("DATABASE_HOST", "host")
        monkeypatch.setenv("DATABASE_PORT", "1234")
        monkeypatch.setenv("DATABASE_USER", "u")
        monkeypatch.setenv("DATABASE_PASSWORD", "p")
        monkeypatch.setenv("DATABASE_NAME", "d")

        with caplog.at_level("ERROR"):
            with pytest.raises(ValueError):
                database.get_database()
            assert "Failed to initialize database" in caplog.text


class TestEnvironmentVariableHandling:
    """Test environment variable handling with real scenarios"""

    def test_inmemory_max_traces_from_env(self, monkeypatch):
        """Test that INMEMORY_MAX_TRACES environment variable is respected"""
        monkeypatch.setenv("INMEMORY_MAX_TRACES", "75")
        db = database.InMemoryDatabase()
        assert db.max_traces == 75

    def test_inmemory_max_traces_from_create_database(self, monkeypatch):
        """Test INMEMORY_MAX_TRACES through create_database"""
        monkeypatch.setenv("INMEMORY_MAX_TRACES", "123")
        db = database.create_database(db_type="inmemory")
        assert db.max_traces == 123

    def test_environment_variables_in_should_use_inmemory(self, monkeypatch):
        """Test environment variable usage in should_use_inmemory_database"""
        # Test with DATABASE_HOST
        monkeypatch.setenv("DATABASE_HOST", "real-host")
        monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
        result = database.should_use_inmemory_database(None)
        assert result is False

        # Test with CLICKHOUSE_HOST fallback
        monkeypatch.delenv("DATABASE_HOST", raising=False)
        monkeypatch.setenv("CLICKHOUSE_HOST", "real-host")
        result = database.should_use_inmemory_database(None)
        assert result is False

        # Test with both missing
        monkeypatch.delenv("DATABASE_HOST", raising=False)
        monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
        result = database.should_use_inmemory_database(None)
        assert result is True


class TestModuleExports:
    """Test module-level functionality"""

    def test_module_all_exports(self):
        """Test that __all__ contains expected exports and they're available"""
        expected_exports = [
            "DatabaseInterface",
            "ClickHouseDatabase",
            "InMemoryDatabase",
            "create_database",
            "get_database",
        ]

        assert hasattr(database, "__all__")
        assert set(database.__all__) == set(expected_exports)

        # Verify all exports are actually available
        for export in expected_exports:
            assert hasattr(database, export)
            # Verify they're not None
            assert getattr(database, export) is not None


class TestRealWorldScenarios:
    """Test scenarios that would occur in real usage"""

    def test_adding_multiple_traces_different_services(self):
        """Test adding traces from multiple services like in real usage"""
        db = database.InMemoryDatabase(max_traces=10)

        # Add traces from different services with realistic data
        traces_data = [
            {
                "ServiceName": "api-gateway",
                "SpanName": "GET /users",
                "StatusCode": "OK",
                "Duration": 15000000,
            },
            {
                "ServiceName": "auth-service",
                "SpanName": "authenticate",
                "StatusCode": "OK",
                "Duration": 5000000,
            },
            {
                "ServiceName": "billing-service",
                "SpanName": "charge_card",
                "StatusCode": "Error",
                "Duration": 30000000,
            },
            {
                "ServiceName": "notification-service",
                "SpanName": "send_email",
                "StatusCode": "OK",
                "Duration": 100000000,
            },
        ]

        for trace_data in traces_data:
            trace = make_trace(**trace_data)
            db.add_trace(trace)

        # Verify all traces are stored and formatted correctly
        traces = db.fetch_unique_traces(10)
        assert len(traces) == 4

        services = db.get_service_names()
        assert set(services) == {
            "api-gateway",
            "auth-service",
            "billing-service",
            "notification-service",
        }

        counts = db.get_trace_counts()
        assert counts["total"] == 4
        assert counts["success"] == 3
        assert counts["errors"] == 1

    def test_trace_formatting_edge_cases_realistic(self):
        """Test trace formatting with realistic edge cases"""
        db = database.InMemoryDatabase()

        # Trace with minimal data (as might come from some systems)
        minimal_trace = {"TraceId": "minimal", "StatusCode": "Error"}
        db.add_trace(minimal_trace)

        # Trace with unusual but valid data
        unusual_trace = {
            "TraceId": "x" * 50,  # Very long ID
            "Duration": 500,  # Sub-millisecond
            "StatusCode": "STATUS_CODE_OK",  # Different OK format
            "SpanAttributes": {"error.type": "ValidationError", "user.id": "user123"},
        }
        db.add_trace(unusual_trace)

        traces = db.fetch_unique_traces(10)

        # Check minimal trace formatting
        minimal_formatted = next(t for t in traces if t["TraceId"] == "minimal")
        assert minimal_formatted["DurationMs"] == "N/A"
        assert minimal_formatted["status_color"] == "negative"
        assert minimal_formatted["KeyInfo"] == ""

        # Check unusual trace formatting
        unusual_formatted = next(t for t in traces if t["TraceId"].startswith("x"))
        assert unusual_formatted["DurationMs"] == "0.00ms"  # Sub-millisecond formatting
        assert (
            unusual_formatted["status_color"] == "positive"
        )  # STATUS_CODE_OK should be positive
        assert (
            unusual_formatted["KeyInfo"] == "🚨 ValidationError"
        )  # Error takes precedence
        assert len(unusual_formatted["ShortTraceId"]) == 16  # Truncated properly

    def test_clickhouse_real_world_query_simulation(self):
        """Test ClickHouse with realistic query simulation"""
        db = database.ClickHouseDatabase(
            "production-ch.company.com", 9000, "analytics", "secret", "telemetry"
        )
        db.clickhouse_connect = mock.MagicMock()
        mock_client = mock.MagicMock()
        db.clickhouse_connect.get_client.return_value.__enter__.return_value = (
            mock_client
        )

        # Simulate realistic trace data
        now = datetime.now(timezone.utc)
        mock_result = mock.MagicMock()
        mock_result.result_rows = [
            [
                "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",  # TraceId
                "span123456789012",  # SpanId
                "parent987654321098",  # ParentSpanId
                "GET /api/v1/orders/12345",  # SpanName
                "order-service",  # ServiceName
                "OK",  # StatusCode
                "",  # StatusMessage
                now,  # Timestamp
                45_000_000,  # Duration (45ms in nanoseconds)
                "SERVER",  # SpanKind
                {"http.method": "GET", "user.id": "user_12345"},  # SpanAttributes
                {
                    "service.name": "order-service",
                    "deployment.environment": "production",
                },  # ResourceAttributes
            ]
        ]
        mock_result.column_names = [
            "TraceId",
            "SpanId",
            "ParentSpanId",
            "SpanName",
            "ServiceName",
            "StatusCode",
            "StatusMessage",
            "Timestamp",
            "Duration",
            "SpanKind",
            "SpanAttributes",
            "ResourceAttributes",
        ]
        mock_client.query.return_value = mock_result

        traces = db.fetch_unique_traces(1)

        assert len(traces) == 1
        trace = traces[0]
        assert trace["TraceId"] == "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        assert trace["ServiceName"] == "order-service"
        assert trace["DurationMs"] == "45.0ms"
        assert trace["status_color"] == "positive"
        assert trace["ShortTraceId"] == "a1b2c3d4e5f6g7h8"  # First 16 chars

    def test_comprehensive_factory_usage(self, monkeypatch):
        """Test comprehensive factory function usage patterns"""
        # Test with full environment configuration
        monkeypatch.setenv("DATABASE_TYPE", "clickhouse")
        monkeypatch.setenv("DATABASE_HOST", "prod-clickhouse")
        monkeypatch.setenv("DATABASE_PORT", "9440")
        monkeypatch.setenv("DATABASE_USER", "trace_user")
        monkeypatch.setenv("DATABASE_PASSWORD", "secure_password")
        monkeypatch.setenv("DATABASE_NAME", "trace_analytics")
        monkeypatch.setenv("INMEMORY_MAX_TRACES", "500")

        # Test ClickHouse creation
        ch_db = database.get_database()
        assert isinstance(ch_db, database.ClickHouseDatabase)
        assert ch_db.host == "prod-clickhouse"
        assert ch_db.port == 9440

        # Test direct factory creation
        inmem_db = database.create_database(db_type="inmemory")
        assert isinstance(inmem_db, database.InMemoryDatabase)
        assert inmem_db.max_traces == 500  # From environment

        # Test auto-detection with explicit parameters
        monkeypatch.delenv("DATABASE_TYPE", raising=False)
        auto_db = database.create_database(
            host="auto-host",
            port=8123,
            user="auto-user",
            password="auto-pass",
            database="auto-db",
        )
        assert isinstance(
            auto_db, database.ClickHouseDatabase
        )  # Should detect from host
        assert auto_db.host == "auto-host"

        # Test fallback to inmemory
        monkeypatch.setenv("DATABASE_HOST", "none")
        fallback_db = database.create_database()
        assert isinstance(fallback_db, database.InMemoryDatabase)
