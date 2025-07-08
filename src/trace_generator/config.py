# config.py
"""Configuration constants and environment variable parsing."""

import os
import logging


class Config:
    """Application configuration constants with database abstraction support"""

    # OpenTelemetry Configuration
    OTLP_ENDPOINT = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"
    )

    # Scenarios Configuration
    # Path to scenarios directory (default: 'scenarios/'). Can be overridden by SCENARIOS_PATH env var.
    SCENARIOS_PATH = os.getenv("SCENARIOS_PATH", "scenarios/")

    # Trace Generation Configuration
    TRACE_INTERVAL_MIN = float(os.getenv("TRACE_INTERVAL_MIN", "0.5"))
    TRACE_INTERVAL_MAX = float(os.getenv("TRACE_INTERVAL_MAX", "2.0"))
    MAX_TEMPLATE_ITERATIONS = int(os.getenv("MAX_TEMPLATE_ITERATIONS", "10"))

    # Database Configuration (Unified)
    DATABASE_TYPE = os.getenv("DATABASE_TYPE", "")  # auto-detect if empty
    DATABASE_HOST = os.getenv("DATABASE_HOST", "") or os.getenv("CLICKHOUSE_HOST", "")
    DATABASE_PORT = int(
        os.getenv("DATABASE_PORT", os.getenv("CLICKHOUSE_PORT", "8123"))
    )
    DATABASE_USER = os.getenv("DATABASE_USER", "") or os.getenv(
        "CLICKHOUSE_USER", "user"
    )
    DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD", "") or os.getenv(
        "CLICKHOUSE_PASSWORD", "password"
    )
    DATABASE_NAME = os.getenv("DATABASE_NAME", "") or os.getenv(
        "CLICKHOUSE_DATABASE", "otel"
    )

    # Legacy ClickHouse Configuration (for backward compatibility)
    CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
    CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "user")
    CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "password")
    CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "otel")

    # In-Memory Database Configuration
    INMEMORY_MAX_TRACES = int(os.getenv("INMEMORY_MAX_TRACES", "100"))

    # Server Configuration
    SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

    # UI Configuration
    TRACE_FETCH_LIMIT = int(os.getenv("TRACE_FETCH_LIMIT", "30"))
    CARD_DISPLAY_LIMIT = int(os.getenv("CARD_DISPLAY_LIMIT", "10"))
    STATUS_UPDATE_INTERVAL = float(os.getenv("STATUS_UPDATE_INTERVAL", "2.0"))

    @classmethod
    def print_config(cls):
        logger = logging.getLogger(__name__)
        logger.info("=== TRACE GENERATOR ENGINE CONFIG ===")
        logger.info(f"UI SERVER: http://{cls.SERVER_HOST}:{cls.SERVER_PORT}")
        logger.info(f"OTLP ENDPOINT: {cls.OTLP_ENDPOINT}")
        logger.info(f"SCENARIOS FILE: {cls.SCENARIOS_PATH}")

        # Database configuration
        db_type = cls._detect_database_type()
        logger.info(f"DATABASE TYPE: {db_type}")

        if db_type == "inmemory":
            logger.info(f"IN-MEMORY MAX TRACES: {cls.INMEMORY_MAX_TRACES}")
        elif db_type == "clickhouse":
            # Use unified config first, fall back to legacy
            host = cls.DATABASE_HOST or cls.CLICKHOUSE_HOST
            port = cls.DATABASE_PORT if cls.DATABASE_HOST else cls.CLICKHOUSE_PORT
            logger.info(f"CLICKHOUSE: {host}:{port}")

        logger.info("FORMAT: Probability 0-100%, Duration in ms")
        logger.info("CONTEXT STORE: Auto-configured based on scenarios")
        logger.info("=====================================")

    @classmethod
    def _detect_database_type(cls) -> str:
        """Detect the database type based on current configuration."""
        # Check explicit database type
        if cls.DATABASE_TYPE:
            return cls.DATABASE_TYPE.lower()

        # Check if host is configured
        host = cls.DATABASE_HOST or cls.CLICKHOUSE_HOST
        if not host or host.lower() in [
            "none",
            "disabled",
            "mock",
            "false",
            "inmemory",
            "memory",
        ]:
            return "inmemory"

        # Default to ClickHouse if host is configured
        return "clickhouse"

    @classmethod
    def get_database_config(cls) -> dict:
        """Get database configuration as a dictionary."""
        return {
            "type": cls._detect_database_type(),
            "host": cls.DATABASE_HOST or cls.CLICKHOUSE_HOST,
            "port": cls.DATABASE_PORT if cls.DATABASE_HOST else cls.CLICKHOUSE_PORT,
            "user": cls.DATABASE_USER or cls.CLICKHOUSE_USER,
            "password": cls.DATABASE_PASSWORD or cls.CLICKHOUSE_PASSWORD,
            "database": cls.DATABASE_NAME or cls.CLICKHOUSE_DATABASE,
            "max_traces": cls.INMEMORY_MAX_TRACES,
        }
