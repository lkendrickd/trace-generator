# validation.py
"""YAML schema validation for trace generator scenarios."""

from typing import Dict, List
import logging
import os
import yaml

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validates scenarios YAML structure with updated probability and duration formats"""

    # Supported schema versions
    SUPPORTED_SCHEMA_VERSIONS = [1]
    CURRENT_SCHEMA_VERSION = 1

    @staticmethod
    def validate_scenarios_config(config: Dict) -> List[str]:
        """Validates the scenarios configuration and returns list of errors"""
        errors = []

        # Validate schema version first
        schema_errors = SchemaValidator._validate_schema_version(config)
        errors.extend(schema_errors)

        if "services" not in config:
            errors.append("Missing required 'services' key")
        elif not isinstance(config["services"], list) or not config["services"]:
            errors.append("'services' must be a non-empty list")

        if "scenarios" not in config:
            errors.append("Missing required 'scenarios' key")
        elif not isinstance(config["scenarios"], list) or not config["scenarios"]:
            errors.append("'scenarios' must be a non-empty list")

        for i, scenario in enumerate(config.get("scenarios", [])):
            scenario_errors = SchemaValidator._validate_scenario(scenario, i)
            errors.extend(scenario_errors)

        return errors

    @staticmethod
    def _validate_schema_version(config: Dict) -> List[str]:
        """Validates the schema version for future compatibility"""
        errors = []

        if "schema_version" not in config:
            errors.append(
                "Missing required 'schema_version' field. Current version is 1."
            )
            return errors

        version = config["schema_version"]
        if not isinstance(version, int):
            errors.append("'schema_version' must be an integer")
            return errors

        if version not in SchemaValidator.SUPPORTED_SCHEMA_VERSIONS:
            supported_versions = ", ".join(
                map(str, SchemaValidator.SUPPORTED_SCHEMA_VERSIONS)
            )
            errors.append(
                f"Unsupported schema version {version}. Supported versions: {supported_versions}"
            )
            return errors

        if version != SchemaValidator.CURRENT_SCHEMA_VERSION:
            logger.warning(
                f"Using schema version {version}, but current version is {SchemaValidator.CURRENT_SCHEMA_VERSION}. "
                f"Consider updating your scenarios file."
            )

        return errors

    @staticmethod
    def _validate_scenario(scenario: Dict, index: int) -> List[str]:
        """Validates a single scenario"""
        errors = []
        prefix = f"scenarios[{index}]"

        if "name" not in scenario:
            errors.append(f"{prefix}: Missing required 'name' field")
        if "root_span" not in scenario:
            errors.append(f"{prefix}: Missing required 'root_span' field")

        if "weight" in scenario and not isinstance(scenario["weight"], (int, float)):
            errors.append(f"{prefix}: 'weight' must be a number")

        if "root_span" in scenario:
            span_errors = SchemaValidator._validate_span_definition(
                scenario["root_span"], f"{prefix}.root_span"
            )
            errors.extend(span_errors)

        return errors

    @staticmethod
    def _validate_span_definition(span_def: Dict, path: str) -> List[str]:
        """Validates a span definition recursively with updated formats"""
        errors = []

        if "service" not in span_def:
            errors.append(f"{path}: Missing required 'service' field")

        if "delay_ms" in span_def:
            delay = span_def["delay_ms"]
            if not isinstance(delay, list) or len(delay) != 2:
                errors.append(
                    f"{path}: 'delay_ms' must be a list of two numbers [min_ms, max_ms]"
                )
            elif not all(isinstance(x, (int, float)) for x in delay):
                errors.append(
                    f"{path}: 'delay_ms' values must be numbers (milliseconds)"
                )
            elif any(x < 0 for x in delay):
                errors.append(f"{path}: 'delay_ms' values must be non-negative")

        # Support legacy 'delay' field for backward compatibility
        if "delay" in span_def:
            delay = span_def["delay"]
            if not isinstance(delay, list) or len(delay) != 2:
                errors.append(
                    f"{path}: 'delay' must be a list of two numbers [min_seconds, max_seconds]"
                )
            elif not all(isinstance(x, (int, float)) for x in delay):
                errors.append(f"{path}: 'delay' values must be numbers (seconds)")

        if "error_conditions" in span_def:
            for i, error_cond in enumerate(span_def["error_conditions"]):
                if not isinstance(error_cond, dict):
                    errors.append(f"{path}.error_conditions[{i}]: Must be a dictionary")
                    continue
                if "type" not in error_cond:
                    errors.append(
                        f"{path}.error_conditions[{i}]: Missing required 'type' field"
                    )
                if "message" not in error_cond:
                    errors.append(
                        f"{path}.error_conditions[{i}]: Missing required 'message' field"
                    )
                if "probability" in error_cond:
                    prob = error_cond["probability"]
                    if not isinstance(prob, (int, float)):
                        errors.append(
                            f"{path}.error_conditions[{i}]: 'probability' must be a number"
                        )
                    elif not (0 <= prob <= 100):
                        errors.append(
                            f"{path}.error_conditions[{i}]: 'probability' must be between 0 and 100 (percentage)"
                        )

        if "calls" in span_def:
            for i, call in enumerate(span_def["calls"]):
                call_errors = SchemaValidator._validate_span_definition(
                    call, f"{path}.calls[{i}]"
                )
                errors.extend(call_errors)

        return errors

    @staticmethod
    def load_scenarios_from_directory(scenarios_dir: str) -> Dict:
        """Load scenarios from a directory containing individual scenario files"""
        if not os.path.exists(scenarios_dir):
            raise FileNotFoundError(f"Scenarios directory not found: {scenarios_dir}")

        if not os.path.isdir(scenarios_dir):
            raise ValueError(f"Path is not a directory: {scenarios_dir}")

        # Load base configuration
        base_config_path = os.path.join(scenarios_dir, "_base.yaml")
        if not os.path.exists(base_config_path):
            raise FileNotFoundError(
                f"Base configuration file not found: {base_config_path}"
            )

        with open(base_config_path, "r") as f:
            merged_config = yaml.safe_load(f)

        if not merged_config:
            merged_config = {}

        # Initialize scenarios list
        merged_config["scenarios"] = []

        # Load all scenario files (excluding _base.yaml)
        scenario_files = []
        for filename in os.listdir(scenarios_dir):
            if filename.endswith(".yaml") and filename != "_base.yaml":
                scenario_files.append(filename)

        # Sort to ensure consistent loading order
        scenario_files.sort()

        logger.info(f"Found {len(scenario_files)} scenario files to load")

        for filename in scenario_files:
            file_path = os.path.join(scenarios_dir, filename)
            try:
                with open(file_path, "r") as f:
                    scenario_data = yaml.safe_load(f)

                if not scenario_data:
                    logger.warning(f"Empty scenario file: {filename}")
                    continue

                # Validate that this is a list of scenarios
                if isinstance(scenario_data, list):
                    merged_config["scenarios"].extend(scenario_data)
                    logger.info(
                        f"Loaded {len(scenario_data)} scenario(s) from {filename}"
                    )
                else:
                    logger.error(
                        f"Invalid scenario file format in {filename}: expected list, got {type(scenario_data)}"
                    )

            except yaml.YAMLError as e:
                logger.error(f"YAML error in {filename}: {e}")
                raise
            except Exception as e:
                logger.error(f"Error loading {filename}: {e}")
                raise

        if not merged_config["scenarios"]:
            raise ValueError("No scenarios found in any scenario files")

        logger.info(
            f"Successfully loaded {len(merged_config['scenarios'])} total scenarios from directory"
        )
        return merged_config
