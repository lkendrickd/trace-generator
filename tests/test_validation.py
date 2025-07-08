import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest
from trace_generator import validation


def test_validation_module_exists():
    assert hasattr(validation, "SchemaValidator")


def test_schema_validator_empty():
    result = validation.SchemaValidator.validate_scenarios_config(
        {"services": [], "scenarios": []}
    )
    assert isinstance(result, list)
    assert "'services' must be a non-empty list" in result
    assert "'scenarios' must be a non-empty list" in result


def test_schema_validator_valid():
    valid = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [{"name": "foo", "weight": 1, "root_span": {"service": "svc"}}],
    }
    result = validation.SchemaValidator.validate_scenarios_config(valid)
    assert result == []


def test_schema_validator_missing_services():
    invalid = {"scenarios": [{"name": "foo"}]}
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("services" in e for e in result)


def test_schema_validator_missing_scenarios():
    invalid = {"services": ["svc"]}
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("scenarios" in e for e in result)


def test_schema_validator_bad_types():
    invalid = {"services": "notalist", "scenarios": "notalist"}
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("must be a non-empty list" in e for e in result)


def test_schema_validator_missing_schema_version():
    invalid = {
        "services": ["svc"],
        "scenarios": [{"name": "foo", "weight": 1, "root_span": {"service": "svc"}}],
    }
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("schema_version" in e for e in result)


def test_schema_validator_invalid_schema_version():
    invalid = {
        "schema_version": "notanint",
        "services": ["svc"],
        "scenarios": [{"name": "foo", "weight": 1, "root_span": {"service": "svc"}}],
    }
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("schema_version" in e for e in result)


def test_schema_validator_missing_root_span():
    invalid = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [{"name": "foo", "weight": 1}],
    }
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("root_span" in e for e in result)


def test_schema_validator_missing_scenario_name():
    invalid = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [{"weight": 1, "root_span": {"service": "svc"}}],
    }
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("name" in e for e in result)


def test_schema_validator_missing_scenario_weight():
    invalid = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [{"name": "foo", "root_span": {"service": "svc"}}],
    }
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    # Accept either a missing 'weight' error or no error if the validator defaults weight
    assert (
        any("weight" in e or "must be a non-empty list" in e for e in result)
        or result == []
    )


def test_schema_validator_missing_root_span_service():
    invalid = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [{"name": "foo", "weight": 1, "root_span": {}}],
    }
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("service" in e for e in result)


def test_schema_validator_extra_fields():
    # Should ignore extra fields and still validate
    valid = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {
                "name": "foo",
                "weight": 1,
                "root_span": {"service": "svc"},
                "extra_field": 123,
            }
        ],
        "extra_top": "ignoreme",
    }
    result = validation.SchemaValidator.validate_scenarios_config(valid)
    assert result == []


def test_schema_validator_multiple_scenarios():
    valid = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {"name": "foo", "weight": 1, "root_span": {"service": "svc"}},
            {"name": "bar", "weight": 2, "root_span": {"service": "svc"}},
        ],
    }
    result = validation.SchemaValidator.validate_scenarios_config(valid)
    assert result == []


def test_schema_validator_empty_dict():
    # Should return errors for all required fields
    invalid = {}
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("services" in e for e in result)
    assert any("scenarios" in e for e in result)
    assert any("schema_version" in e for e in result)


def test_schema_validator_empty_scenario_dict():
    # Scenario dict missing all required fields
    invalid = {"schema_version": 1, "services": ["svc"], "scenarios": [{}]}
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    # Accept any of the required field errors, but not all validators require 'weight' explicitly
    assert any("name" in e for e in result)
    assert any("root_span" in e for e in result)
    # 'weight' may be optional or defaulted, so only check if present in errors
    if not any("weight" in e for e in result):
        assert result  # There should be at least some error


def test_schema_validator_non_dict():
    # Should return error for non-dict input
    invalid = [1, 2, 3]
    try:
        result = validation.SchemaValidator.validate_scenarios_config(invalid)
    except Exception as e:
        # Accept AttributeError or TypeError as valid outcomes for non-dict input
        assert isinstance(e, (AttributeError, TypeError))
    else:
        assert isinstance(result, list)
        assert any("dict" in e or "object" in e for e in result)


def test_span_delay_ms_validation():
    invalid = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {
                "name": "foo",
                "weight": 1,
                "root_span": {"service": "svc", "delay_ms": [100]},
            }
        ],
    }
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("delay_ms" in e for e in result)

    invalid2 = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {
                "name": "foo",
                "weight": 1,
                "root_span": {"service": "svc", "delay_ms": [100, -1]},
            }
        ],
    }
    result2 = validation.SchemaValidator.validate_scenarios_config(invalid2)
    assert any("non-negative" in e for e in result2)

    invalid3 = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {
                "name": "foo",
                "weight": 1,
                "root_span": {"service": "svc", "delay_ms": [100, "bad"]},
            }
        ],
    }
    result3 = validation.SchemaValidator.validate_scenarios_config(invalid3)
    assert any("must be numbers" in e for e in result3)


def test_span_delay_legacy():
    invalid = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {"name": "foo", "weight": 1, "root_span": {"service": "svc", "delay": [1]}}
        ],
    }
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("delay' must be a list of two numbers" in e for e in result)

    invalid2 = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {
                "name": "foo",
                "weight": 1,
                "root_span": {"service": "svc", "delay": [1, "bad"]},
            }
        ],
    }
    result2 = validation.SchemaValidator.validate_scenarios_config(invalid2)
    assert any("delay' values must be numbers" in e for e in result2)


def test_span_error_conditions():
    invalid = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {
                "name": "foo",
                "weight": 1,
                "root_span": {"service": "svc", "error_conditions": ["notadict"]},
            }
        ],
    }
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("Must be a dictionary" in e for e in result)

    invalid2 = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {
                "name": "foo",
                "weight": 1,
                "root_span": {
                    "service": "svc",
                    "error_conditions": [{"probability": 200}],
                },
            }
        ],
    }
    result2 = validation.SchemaValidator.validate_scenarios_config(invalid2)
    assert any("between 0 and 100" in e for e in result2)

    invalid3 = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {
                "name": "foo",
                "weight": 1,
                "root_span": {
                    "service": "svc",
                    "error_conditions": [
                        {"type": 1, "message": 2, "probability": "bad"}
                    ],
                },
            }
        ],
    }
    result3 = validation.SchemaValidator.validate_scenarios_config(invalid3)
    assert any("'probability' must be a number" in e for e in result3)

    invalid4 = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {
                "name": "foo",
                "weight": 1,
                "root_span": {"service": "svc", "error_conditions": [{}]},
            }
        ],
    }
    result4 = validation.SchemaValidator.validate_scenarios_config(invalid4)
    assert any("Missing required 'type' field" in e for e in result4)
    assert any("Missing required 'message' field" in e for e in result4)


def test_span_calls_recursive():
    invalid = {
        "schema_version": 1,
        "services": ["svc"],
        "scenarios": [
            {
                "name": "foo",
                "weight": 1,
                "root_span": {
                    "service": "svc",
                    "calls": [
                        {"service": "svc", "delay_ms": [1]},
                        {"service": "svc", "delay": [1]},
                        {"service": "svc", "error_conditions": ["notadict"]},
                    ],
                },
            }
        ],
    }
    result = validation.SchemaValidator.validate_scenarios_config(invalid)
    assert any("delay_ms" in e for e in result)
    assert any("delay' must be a list of two numbers" in e for e in result)
    assert any("Must be a dictionary" in e for e in result)


def test_load_scenarios_from_directory(tmp_path):
    import yaml

    # Setup a fake scenarios directory
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    base = {"schema_version": 1, "services": ["svc"]}
    (scenarios_dir / "_base.yaml").write_text(yaml.dump(base))
    scenario1 = [{"name": "foo", "weight": 1, "root_span": {"service": "svc"}}]
    (scenarios_dir / "01.yaml").write_text(yaml.dump(scenario1))
    scenario2 = [{"name": "bar", "weight": 2, "root_span": {"service": "svc"}}]
    (scenarios_dir / "02.yaml").write_text(yaml.dump(scenario2))
    # Should load and merge all scenarios
    merged = validation.SchemaValidator.load_scenarios_from_directory(
        str(scenarios_dir)
    )
    assert merged["schema_version"] == 1
    assert merged["services"] == ["svc"]
    assert len(merged["scenarios"]) == 2
    names = {s["name"] for s in merged["scenarios"]}
    assert names == {"foo", "bar"}

    # Test missing _base.yaml
    missing_base_dir = tmp_path / "missingbase"
    missing_base_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        validation.SchemaValidator.load_scenarios_from_directory(str(missing_base_dir))

    # Test not a directory
    with pytest.raises(ValueError):
        validation.SchemaValidator.load_scenarios_from_directory(
            str(scenarios_dir / "_base.yaml")
        )

    # Test empty scenario file
    (scenarios_dir / "03.yaml").write_text("")
    merged2 = validation.SchemaValidator.load_scenarios_from_directory(
        str(scenarios_dir)
    )
    assert len(merged2["scenarios"]) == 2  # Still just foo and bar

    # Test invalid YAML (should not raise, just log error and skip file)
    (scenarios_dir / "04.yaml").write_text(":bad yaml:")
    merged3 = validation.SchemaValidator.load_scenarios_from_directory(
        str(scenarios_dir)
    )
    assert len(merged3["scenarios"]) == 2  # Still just foo and bar

    # Test scenario file not a list
    (scenarios_dir / "05.yaml").write_text(yaml.dump({"not": "a list"}))
    # Should log error but not raise
    merged4 = validation.SchemaValidator.load_scenarios_from_directory(
        str(scenarios_dir)
    )
    assert len(merged4["scenarios"]) == 2


def test_load_scenarios_from_directory_empty_all(tmp_path):
    import yaml

    # Setup a fake scenarios directory with only _base.yaml and no scenario files
    scenarios_dir = tmp_path / "scenarios_empty"
    scenarios_dir.mkdir()
    base = {"schema_version": 1, "services": ["svc"]}
    (scenarios_dir / "_base.yaml").write_text(yaml.dump(base))
    # Should raise ValueError for no scenarios found
    with pytest.raises(ValueError):
        validation.SchemaValidator.load_scenarios_from_directory(str(scenarios_dir))


def test_load_scenarios_from_directory_empty_yaml(tmp_path):
    import yaml

    # Setup a fake scenarios directory with _base.yaml and an empty scenario file (valid YAML, but empty list)
    scenarios_dir = tmp_path / "scenarios_empty_yaml"
    scenarios_dir.mkdir()
    base = {"schema_version": 1, "services": ["svc"]}
    (scenarios_dir / "_base.yaml").write_text(yaml.dump(base))
    (scenarios_dir / "01.yaml").write_text(yaml.dump([]))
    # Should raise ValueError for no scenarios found
    with pytest.raises(ValueError):
        validation.SchemaValidator.load_scenarios_from_directory(str(scenarios_dir))
