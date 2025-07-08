import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from trace_generator import data


class DummyDB:
    def __init__(self):
        self.host = "localhost"
        self.port = 1234

    def fetch_unique_traces(self, limit=10):
        return [{"trace_id": "abc", "service": "svc", "span_id": "span1"}]

    def get_trace_counts(self):
        return {"total": 1}

    def get_service_names(self):
        return ["svc"]

    def health_check(self):
        return True


class TestTraceDataService:
    def test_data_module_exists(self):
        assert hasattr(data, "TraceDataService")

    def test_fetch_unique_traces(self):
        ds = data.TraceDataService(DummyDB())
        traces = ds.fetch_unique_traces()
        assert isinstance(traces, list)
        assert traces[0]["trace_id"] == "abc"

    def test_get_trace_counts(self):
        ds = data.TraceDataService(DummyDB())
        counts = ds.get_trace_counts()
        assert counts["total"] == 1

    def test_get_service_names(self):
        ds = data.TraceDataService(DummyDB())
        names = ds.get_service_names()
        assert names == ["svc"]

    def test_get_database_info(self):
        ds = data.TraceDataService(DummyDB())
        info = ds.get_database_info()
        assert isinstance(info, dict)
        assert "type" in info
        assert "host" in info
        assert "port" in info

    def test_fetch_unique_traces_error(self, caplog):
        class FailingDB(DummyDB):
            def fetch_unique_traces(self, limit=10):
                raise Exception("fail")

        ds = data.TraceDataService(FailingDB())
        with caplog.at_level("ERROR"):
            traces = ds.fetch_unique_traces()
            assert traces == []
            assert "Error fetching traces" in caplog.text

    def test_get_trace_counts_error(self, caplog):
        class FailingDB(DummyDB):
            def get_trace_counts(self):
                raise Exception("fail")

        ds = data.TraceDataService(FailingDB())
        with caplog.at_level("ERROR"):
            counts = ds.get_trace_counts()
            assert counts == {"total": 0, "errors": 0, "success": 0}
            assert "Error getting trace counts" in caplog.text

    def test_get_service_names_error(self, caplog):
        class FailingDB(DummyDB):
            def get_service_names(self):
                raise Exception("fail")

        ds = data.TraceDataService(FailingDB())
        with caplog.at_level("ERROR"):
            names = ds.get_service_names()
            assert names == []
            assert "Error getting service names" in caplog.text

    def test_add_trace_success_and_error(self, caplog):
        class DummyAddDB(DummyDB):
            def add_trace(self, trace):
                self.added = trace

        db = DummyAddDB()
        ds = data.TraceDataService(db)
        ds.add_trace({"TraceId": "t"})
        assert hasattr(db, "added")

        class FailingAddDB(DummyDB):
            def add_trace(self, trace):
                raise Exception("fail")

        ds = data.TraceDataService(FailingAddDB())
        with caplog.at_level("ERROR"):
            ds.add_trace({"TraceId": "t"})
            assert "Error adding trace" in caplog.text

    def test_count_error_traces(self):
        ds = data.TraceDataService(DummyDB())
        traces = [
            {"StatusCode": "OK"},
            {"StatusCode": "ERROR"},
            {"StatusCode": "foo"},
            {},
        ]
        assert ds.count_error_traces(traces) == 3

    def test_health_check_success_and_error(self, caplog):
        ds = data.TraceDataService(DummyDB())
        assert ds.health_check() is True

        class FailingHealthDB(DummyDB):
            def health_check(self):
                raise Exception("fail")

        ds = data.TraceDataService(FailingHealthDB())
        with caplog.at_level("ERROR"):
            assert ds.health_check() is False
            assert "Database health check failed" in caplog.text

    def test_get_database_info_variants(self):
        class DBWithMax(DummyDB):
            max_traces = 42

        ds = data.TraceDataService(DBWithMax())
        info = ds.get_database_info()
        assert info["max_traces"] == 42

        # No host/port
        class DBNoHost:
            def health_check(self):
                return True

        ds = data.TraceDataService(DBNoHost())
        info = ds.get_database_info()
        assert "host" not in info and "port" not in info


class TestTraceDataServiceWithInMemoryDB:
    def setup_method(self):
        from trace_generator.database import InMemoryDatabase

        self.db = InMemoryDatabase()
        self.ds = data.TraceDataService(self.db)

    def test_add_and_fetch_trace(self):
        trace = {
            "TraceId": "t1",
            "SpanId": "s1",
            "ServiceName": "svc",
            "SpanName": "span",
            "StatusCode": "OK",
            "Timestamp": None,
            "Duration": 1000,
        }
        self.ds.add_trace(trace)
        traces = self.ds.fetch_unique_traces()
        assert any(t["TraceId"] == "t1" for t in traces)

    def test_get_trace_counts_and_services(self):
        self.ds.add_trace(
            {
                "TraceId": "t2",
                "SpanId": "s2",
                "ServiceName": "svc2",
                "StatusCode": "ERROR",
                "SpanName": "span",
                "Timestamp": None,
                "Duration": 1000,
            }
        )
        counts = self.ds.get_trace_counts()
        assert counts["total"] >= 1
        assert "errors" in counts and "success" in counts
        services = self.ds.get_service_names()
        assert "svc2" in services

    def test_health_check_and_disconnect(self):
        assert self.ds.health_check() is True
        self.db.disconnect()
        # After disconnect, DB is empty but health_check should still return True (by design)
        assert self.ds.health_check() is True
        assert self.ds.fetch_unique_traces() != []  # Should return sample traces

    def test_add_trace_missing_fields(self):
        # Should not raise, just add with missing fields
        self.ds.add_trace({"TraceId": "t3"})
        traces = self.ds.fetch_unique_traces()
        assert any("TraceId" in t for t in traces)

    def test_get_database_info_inmemory(self):
        info = self.ds.get_database_info()
        assert info["type"] == "InMemoryDatabase"
        assert info["healthy"] is True
        assert info["supports_direct_insert"] is True
        assert "max_traces" in info

    def test_sample_traces_when_empty(self):
        self.db.traces.clear()
        traces = self.ds.fetch_unique_traces(2)
        assert len(traces) == 2
        assert all("ServiceName" in t for t in traces)

    def test_add_trace_and_counts_after_disconnect(self):
        self.ds.add_trace(
            {
                "TraceId": "t4",
                "SpanId": "s4",
                "ServiceName": "svc4",
                "StatusCode": "OK",
                "SpanName": "span",
                "Timestamp": None,
                "Duration": 1000,
            }
        )
        self.db.disconnect()
        # After disconnect, traces should be sample traces
        traces = self.ds.fetch_unique_traces()
        assert any("ServiceName" in t for t in traces)
