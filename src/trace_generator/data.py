# data.py
"""Data access service for trace generator using the unified database abstraction."""

from typing import List, Dict, Any
import logging
from trace_generator.database import get_database, DatabaseInterface


class TraceDataService:
    """Service layer for accessing trace data through the database abstraction."""

    def __init__(self, db: DatabaseInterface = None):
        self.db = db or get_database()
        self.logger = logging.getLogger(__name__)

        # Log the database type being used
        db_type = type(self.db).__name__
        self.logger.info(f"TraceDataService initialized with {db_type}")

    def fetch_unique_traces(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Fetch unique traces from the configured database."""
        try:
            traces = self.db.fetch_unique_traces(limit)
            self.logger.debug(f"Fetched {len(traces)} traces from database")
            return traces
        except Exception as e:
            self.logger.error(f"Error fetching traces: {e}")
            return []

    def get_trace_counts(self) -> Dict[str, int]:
        """Get trace count statistics from the database."""
        try:
            counts = self.db.get_trace_counts()
            self.logger.debug(f"Retrieved trace counts: {counts}")
            return counts
        except Exception as e:
            self.logger.error(f"Error getting trace counts: {e}")
            return {"total": 0, "errors": 0, "success": 0}

    def get_service_names(self) -> List[str]:
        """Get list of service names from the database."""
        try:
            services = self.db.get_service_names()
            self.logger.debug(f"Retrieved {len(services)} service names")
            return services
        except Exception as e:
            self.logger.error(f"Error getting service names: {e}")
            return []

    def add_trace(self, trace: Dict[str, Any]) -> None:
        """Add a trace to the database (mainly for in-memory database)."""
        try:
            self.db.add_trace(trace)
            self.logger.debug(
                f"Added trace to database: {trace.get('TraceId', 'unknown')[:16]}"
            )
        except Exception as e:
            self.logger.error(f"Error adding trace: {e}")

    def count_error_traces(self, traces: List[Dict[str, Any]]) -> int:
        """Count error traces in the provided list."""
        return len(
            [
                t
                for t in traces
                if t.get("StatusCode", "").upper() not in ["OK", "STATUS_CODE_OK"]
            ]
        )

    def health_check(self) -> bool:
        """Check if the database connection is healthy."""
        try:
            return self.db.health_check()
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            return False

    def get_database_info(self) -> Dict[str, Any]:
        """Get information about the current database configuration."""
        db_type = type(self.db).__name__
        health = self.health_check()

        info = {
            "type": db_type,
            "healthy": health,
            "supports_direct_insert": db_type == "InMemoryDatabase",
        }

        if hasattr(self.db, "max_traces"):
            info["max_traces"] = self.db.max_traces
        if hasattr(self.db, "host"):
            info["host"] = self.db.host
            info["port"] = self.db.port

        return info
