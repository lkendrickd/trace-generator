import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import importlib

from trace_generator import config


class TestConfig:
    def test_otlp_endpoint_default(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        importlib.reload(config)
        assert config.Config.OTLP_ENDPOINT == "http://otel-collector:4317"

    def test_scenarios_path_env_override(self, monkeypatch):
        monkeypatch.setenv("SCENARIOS_PATH", "custom_scenarios/")
        importlib.reload(config)
        assert config.Config.SCENARIOS_PATH == "custom_scenarios/"
        monkeypatch.delenv("SCENARIOS_PATH", raising=False)
        importlib.reload(config)

    def test_trace_interval_min_max(self, monkeypatch):
        monkeypatch.setenv("TRACE_INTERVAL_MIN", "1.5")
        monkeypatch.setenv("TRACE_INTERVAL_MAX", "3.5")
        importlib.reload(config)
        assert config.Config.TRACE_INTERVAL_MIN == 1.5
        assert config.Config.TRACE_INTERVAL_MAX == 3.5
        monkeypatch.delenv("TRACE_INTERVAL_MIN", raising=False)
        monkeypatch.delenv("TRACE_INTERVAL_MAX", raising=False)
        importlib.reload(config)

    def test_database_type_detection(self, monkeypatch):
        monkeypatch.setenv("DATABASE_TYPE", "clickhouse")
        importlib.reload(config)
        assert config.Config._detect_database_type() == "clickhouse"
        monkeypatch.setenv("DATABASE_TYPE", "inmemory")
        importlib.reload(config)
        assert config.Config._detect_database_type() == "inmemory"
        monkeypatch.delenv("DATABASE_TYPE", raising=False)
        importlib.reload(config)

    def test_get_database_config_keys(self):
        db_cfg = config.Config.get_database_config()
        for key in [
            "type",
            "host",
            "port",
            "user",
            "password",
            "database",
            "max_traces",
        ]:
            assert key in db_cfg

    def test_print_config_runs(self, caplog):
        caplog.set_level("INFO")
        config.Config.print_config()
        assert "TRACE GENERATOR ENGINE CONFIG" in caplog.text

    def test_inmemory_max_traces_default(self, monkeypatch):
        monkeypatch.delenv("INMEMORY_MAX_TRACES", raising=False)
        importlib.reload(config)
        assert config.Config.INMEMORY_MAX_TRACES == 100

    def test_server_port_and_host_defaults(self, monkeypatch):
        monkeypatch.delenv("SERVER_HOST", raising=False)
        monkeypatch.delenv("SERVER_PORT", raising=False)
        importlib.reload(config)
        assert config.Config.SERVER_HOST == "0.0.0.0"
        assert config.Config.SERVER_PORT == 8000

    def test_ui_config_defaults(self, monkeypatch):
        monkeypatch.delenv("TRACE_FETCH_LIMIT", raising=False)
        monkeypatch.delenv("CARD_DISPLAY_LIMIT", raising=False)
        monkeypatch.delenv("STATUS_UPDATE_INTERVAL", raising=False)
        importlib.reload(config)
        assert config.Config.TRACE_FETCH_LIMIT == 30
        assert config.Config.CARD_DISPLAY_LIMIT == 10
        assert config.Config.STATUS_UPDATE_INTERVAL == 2.0
