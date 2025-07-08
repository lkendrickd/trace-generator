#!/usr/bin/env python3
"""
OpenTelemetry Compliant Trace Generator - CONFIG-DRIVEN ENGINE
This script dynamically generates OpenTelemetry traces based on scenarios
defined in a YAML file. It supports complex, multi-span traces, error
simulation, and a live UI for monitoring trace generation.

UPDATED: Now supports both ClickHouse and in-memory database backends with
automatic fallback and proper integration between trace generation and storage.
"""

import sys
import os
import logging
import atexit
import yaml

# Import from modules
from trace_generator.config import Config
from trace_generator.validation import SchemaValidator
from trace_generator.engine import (
    setup_opentelemetry_providers,
    shutdown_opentelemetry_providers,
    TraceGenerator,
)
from trace_generator.data import TraceDataService
from trace_generator.database import get_database
from trace_generator.ui import TraceUI

# =========================================================================
#                           LOGGING SETUP
# =========================================================================
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

logger.info("Starting OpenTelemetry Trace Generator...")


def main():
    """Main application entry point"""
    Config.print_config()

    # Initialize database first
    try:
        database = get_database()
        logger.info(f"Database initialized: {type(database).__name__}")

        # Test database connection
        if not database.health_check():
            logger.warning("Database health check failed, but continuing...")
            sys.exit(1)
            return
        else:
            logger.info("Database health check passed")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)
        return

    # Load and validate scenarios
    try:
        # Always resolve scenarios relative to project root, not module
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../")
        )
        # If SCENARIOS_DIR is set, use it (absolute or relative to project root). Otherwise, default to '/app/scenarios' if it exists, else fallback to project_root/scenarios.
        scenarios_dir_env = os.environ.get("SCENARIOS_DIR")
        if scenarios_dir_env:
            if os.path.isabs(scenarios_dir_env):
                scenarios_dir = scenarios_dir_env
            else:
                scenarios_dir = os.path.abspath(
                    os.path.join(project_root, scenarios_dir_env)
                )
        else:
            # For testability: if neither /app/scenarios nor project_root/scenarios exist, fallback to project_root (so fallback file logic works in tests)
            docker_default = "/app/scenarios"
            local_default = os.path.join(project_root, "scenarios")
            if os.path.isdir(docker_default):
                scenarios_dir = docker_default
            elif os.path.isdir(local_default):
                scenarios_dir = local_default
            else:
                # Fallback to project_root so fallback file logic can still find _base.yaml or scenarios.yaml in tests
                # But if those files don't exist, fallback to current working directory for test mocks
                scenarios_dir = os.getcwd()

        logger.info(f"Resolved scenarios_dir: {scenarios_dir}")

        if os.path.isdir(scenarios_dir):
            # Load from directory
            scenarios_config = SchemaValidator.load_scenarios_from_directory(
                scenarios_dir
            )
            logging.info(
                f"Successfully loaded scenarios from directory {scenarios_dir}"
            )
        else:
            # Fallback to a single file (try _base.yaml, then scenarios.yaml)
            for fallback_file in ("_base.yaml", "scenarios.yaml"):
                scenarios_file = os.path.join(scenarios_dir, fallback_file)
                if os.path.exists(scenarios_file):
                    with open(scenarios_file, "r") as f:
                        scenarios_config = yaml.safe_load(f)
                    logging.info(f"Successfully loaded scenarios from {scenarios_file}")
                    break
            else:
                raise FileNotFoundError(
                    f"No scenarios directory or fallback file found in {scenarios_dir}"
                )

        validation_errors = SchemaValidator.validate_scenarios_config(scenarios_config)
        if validation_errors:
            logging.error("YAML validation errors found:")
            for error in validation_errors:
                logging.error(f"  - {error}")
            logging.error("Please fix the scenarios file and restart.")
            sys.exit(1)
            return
        else:
            logging.info("Scenarios configuration validated successfully")
    except FileNotFoundError as e:
        logging.error(f"FATAL: Scenarios file or directory not found: {e}. Exiting.")
        sys.exit(1)
        return
    except yaml.YAMLError as e:
        logging.error(f"FATAL: Error parsing YAML: {e}. Exiting.")
        sys.exit(1)
        return
    except Exception as e:
        logging.error(f"FATAL: Error loading scenarios: {e}. Exiting.")
        sys.exit(1)
        return

    # Get service list from scenarios
    service_list = scenarios_config.get("services", [])
    if not service_list:
        logging.error("FATAL: No 'services' defined in scenarios file. Exiting.")
        sys.exit(1)

    # Setup OpenTelemetry with database integration
    tracers = setup_opentelemetry_providers(service_list, database)

    # Initialize trace generator with database
    num_workers = int(os.getenv("TRACE_NUM_WORKERS", "4"))
    trace_generator = TraceGenerator(
        tracers, scenarios_config, num_workers=num_workers, database=database
    )

    # Initialize data service with the same database instance
    trace_data_service = TraceDataService(database)

    # Initialize UI
    trace_ui = TraceUI(
        trace_generator, scenarios_config, trace_data_service=trace_data_service
    )

    # Setup web interface
    from nicegui import ui

    @ui.page("/health")
    def health_check():
        generator_status = trace_generator.get_status()
        db_info = trace_data_service.get_database_info()
        return {
            "status": "healthy",
            "trace_generator_status": generator_status,
            "database_info": db_info,
        }

    @ui.page("/")
    def main_page():
        trace_ui.create_main_page()

    # Start trace generation automatically
    logging.info("Starting trace generation engine automatically...")
    trace_generator.start()

    # Setup cleanup
    def cleanup():
        trace_generator.stop()
        shutdown_opentelemetry_providers()
        if hasattr(database, "disconnect"):
            database.disconnect()

    atexit.register(cleanup)

    # Log startup information
    db_type = type(database).__name__
    logger.info("=== Startup Complete ===")
    logger.info(f"Database: {db_type}")
    logger.info(f"Services: {len(service_list)} configured")
    logger.info(f"Scenarios: {len(scenarios_config.get('scenarios', []))} loaded")
    logger.info(f"Workers: {num_workers} trace generation threads")
    logger.info(f"UI Server: http://{Config.SERVER_HOST}:{Config.SERVER_PORT}")

    if db_type == "InMemoryDatabase":
        max_traces = getattr(database, "max_traces", 100)
        logger.info(f"In-Memory Mode: Storing up to {max_traces} traces")
        logger.info("Note: Traces are stored in memory only (no persistence)")

    logger.info("========================")

    # Start the web server
    logging.info(
        f"Starting NiceGUI server on {Config.SERVER_HOST}:{Config.SERVER_PORT}..."
    )
    ui.run(
        host=Config.SERVER_HOST,
        port=Config.SERVER_PORT,
        title="OTel Trace Generator Engine",
        dark=None,
        favicon="⚙️",
        reload=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
