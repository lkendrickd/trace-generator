import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from unittest import mock
import importlib


# Helper to patch all dependencies used in main.py
def patch_main_dependencies(
    monkeypatch, db_ok=True, scenario_ok=True, validation_ok=True, services_ok=True
):
    # Patch Config.print_config
    monkeypatch.setattr("trace_generator.config.Config.print_config", lambda: None)
    # Patch get_database
    DummyDB = type(
        "DummyDB",
        (),
        {"health_check": lambda self: db_ok, "disconnect": lambda self: None},
    )
    monkeypatch.setattr("trace_generator.database.get_database", lambda: DummyDB())
    # Patch SchemaValidator
    dummy_scenarios = {
        "services": ["svc1"] if services_ok else [],
        "scenarios": [{"name": "s1"}],
    }
    monkeypatch.setattr(
        "trace_generator.validation.SchemaValidator.load_scenarios_from_directory",
        lambda _: dummy_scenarios
        if scenario_ok
        else (_ for _ in ()).throw(FileNotFoundError("not found")),
    )
    monkeypatch.setattr(
        "trace_generator.validation.SchemaValidator.validate_scenarios_config",
        lambda _: [] if validation_ok else ["err"],
    )
    # Patch TraceGenerator
    DummyTG = type(
        "DummyTG",
        (),
        {
            "get_status": lambda self: {
                "running": True,
                "trace_count": 1,
                "services_configured": 1,
            },
            "start": lambda self: None,
            "stop": lambda self: None,
        },
    )
    monkeypatch.setattr(
        "trace_generator.engine.TraceGenerator", lambda *a, **kw: DummyTG()
    )
    monkeypatch.setattr(
        "trace_generator.engine.setup_opentelemetry_providers", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "trace_generator.engine.shutdown_opentelemetry_providers", lambda: None
    )
    # Patch TraceDataService
    monkeypatch.setattr("trace_generator.data.TraceDataService", lambda db: mock.Mock())
    # Patch TraceUI
    monkeypatch.setattr(
        "trace_generator.ui.TraceUI",
        lambda *a, **kw: mock.Mock(create_main_page=lambda: None),
    )
    # Patch nicegui.ui
    dummy_ui = mock.Mock()
    dummy_ui.page = lambda *a, **kw: lambda f: f
    dummy_ui.run = lambda **kw: None
    monkeypatch.setitem(sys.modules, "nicegui", mock.Mock(ui=dummy_ui))
    monkeypatch.setitem(sys.modules, "nicegui.ui", dummy_ui)
    return dummy_ui


def test_main_success(monkeypatch):
    patch_main_dependencies(monkeypatch)
    import trace_generator.main as main

    importlib.reload(main)
    # Patch os.path.exists, os.path.isdir, and open to simulate scenarios directory/file
    monkeypatch.setattr(main.os.path, "exists", lambda p: True)
    monkeypatch.setattr(main.os.path, "isdir", lambda p: True)
    monkeypatch.setattr(
        "builtins.open",
        lambda *a, **kw: mock.mock_open(
            read_data="services: [svc1]\nscenarios: []"
        ).return_value,
    )
    # Should run main() without error
    main.main()


def test_main_db_fail(monkeypatch):
    patch_main_dependencies(monkeypatch, db_ok=False)
    import trace_generator.main as main

    importlib.reload(main)
    with mock.patch("sys.exit") as exit_mock:
        main.main()
        exit_mock.assert_called_once()


def test_main_scenarios_not_found(monkeypatch):
    patch_main_dependencies(monkeypatch, scenario_ok=False)
    import trace_generator.main as main

    importlib.reload(main)
    with mock.patch("sys.exit") as exit_mock:
        main.main()
        exit_mock.assert_called_once()


def test_main_validation_error(monkeypatch):
    patch_main_dependencies(monkeypatch, validation_ok=False)
    import trace_generator.main as main

    importlib.reload(main)
    with mock.patch("sys.exit") as exit_mock:
        main.main()
        exit_mock.assert_called_once()


def test_main_no_services(monkeypatch):
    patch_main_dependencies(monkeypatch, services_ok=False)
    import trace_generator.main as main

    importlib.reload(main)
    with mock.patch("sys.exit") as exit_mock:
        main.main()
        exit_mock.assert_called_once()


def test_main_fallback_to_file(monkeypatch):
    patch_main_dependencies(monkeypatch)
    import trace_generator.main as main

    importlib.reload(main)
    # Simulate scenarios directory missing, fallback to file
    monkeypatch.setattr(
        main.os.path,
        "exists",
        lambda p: True
        if p.endswith("scenarios.yaml") or p.endswith("_base.yaml")
        else False,
    )
    monkeypatch.setattr(main.os.path, "isdir", lambda p: False)
    monkeypatch.setattr(
        "builtins.open", mock.mock_open(read_data="services: [svc1]\nscenarios: []")
    )
    main.main()


def test_main_file_not_found(monkeypatch):
    patch_main_dependencies(monkeypatch)
    import trace_generator.main as main

    importlib.reload(main)
    monkeypatch.setattr(main.os.path, "exists", lambda p: False)
    monkeypatch.setattr(main.os.path, "isdir", lambda p: False)
    monkeypatch.setattr(
        "builtins.open", mock.Mock(side_effect=FileNotFoundError("not found"))
    )
    with mock.patch("sys.exit") as exit_mock:
        main.main()
        exit_mock.assert_called_once()


def test_main_yaml_error(monkeypatch):
    patch_main_dependencies(monkeypatch)
    import trace_generator.main as main

    importlib.reload(main)
    monkeypatch.setattr(main.os.path, "exists", lambda p: False)
    monkeypatch.setattr(main.os.path, "isdir", lambda p: False)
    # Patch open to succeed, but yaml.safe_load to raise
    monkeypatch.setattr("builtins.open", mock.mock_open(read_data="bad: ["))
    monkeypatch.setattr(
        main.yaml, "safe_load", mock.Mock(side_effect=main.yaml.YAMLError("bad yaml"))
    )
    with mock.patch("sys.exit") as exit_mock:
        main.main()
        exit_mock.assert_called_once()


def test_main_generic_exception(monkeypatch):
    patch_main_dependencies(monkeypatch)
    import trace_generator.main as main

    importlib.reload(main)
    monkeypatch.setattr(main.os.path, "exists", lambda p: False)
    monkeypatch.setattr(main.os.path, "isdir", lambda p: False)
    # Patch open to raise generic Exception
    monkeypatch.setattr("builtins.open", mock.Mock(side_effect=Exception("boom")))
    with mock.patch("sys.exit") as exit_mock:
        main.main()
        exit_mock.assert_called_once()


def test_main_ui_and_cleanup(monkeypatch):
    # This covers the UI and cleanup logic (atexit, TraceUI, etc)
    patch_main_dependencies(monkeypatch)
    import trace_generator.main as main

    importlib.reload(main)
    monkeypatch.setattr(main.os.path, "exists", lambda p: True)
    monkeypatch.setattr(main.os.path, "isdir", lambda p: True)
    monkeypatch.setattr(
        "builtins.open", mock.mock_open(read_data="services: [svc1]\nscenarios: []")
    )
    # Patch atexit.register to call the cleanup immediately for coverage
    monkeypatch.setattr(main.atexit, "register", lambda f: f())
    main.main()
