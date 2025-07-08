import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from trace_generator import resolver


def test_resolver_module_exists():
    assert hasattr(resolver, "resolve_template")


def test_resolve_template_basic():
    template = "Hello, {{name}}!"
    context = {"name": "World"}
    assert resolver.resolve_template(template, context) == "Hello, World!"


def test_resolve_template_no_vars():
    template = "No variables here."
    context = {}
    assert resolver.resolve_template(template, context) == "No variables here."


def test_resolve_template_missing_var():
    template = "Hi, {{missing}}!"
    context = {}
    # Should not raise, just leave as is or blank
    result = resolver.resolve_template(template, context)
    assert "{{missing}}" in result or result == "Hi, !"


def test_template_nested_vars():
    template = "User: {{user.id}}, Session: {{session.id}}"
    context = {"user.id": "u1", "session.id": "s1"}
    assert resolver.resolve_template(template, context) == "User: u1, Session: s1"


def test_template_multiple_same_var():
    template = "{{foo}}, {{foo}}, {{foo}}"
    context = {"foo": "bar"}
    assert resolver.resolve_template(template, context) == "bar, bar, bar"


def test_template_missing_and_present():
    template = "{{present}}-{{missing}}"
    context = {"present": "yes"}
    result = resolver.resolve_template(template, context)
    assert result.startswith("yes-")


def test_resolve_random_int(monkeypatch):
    # Patch random.randint to always return 42
    monkeypatch.setattr("random.randint", lambda a, b: 42)
    template = "Random: {{random.int(1,100)}}"
    context = {}
    result = resolver.resolve_template(template, context)
    assert result == "Random: 42"


def test_resolve_random_float(monkeypatch):
    # Patch random.uniform to always return 3.1415
    monkeypatch.setattr("random.uniform", lambda a, b: 3.1415)
    template = "Float: {{random.float(1.0,5.0)}}"
    context = {}
    result = resolver.resolve_template(template, context)
    assert result.startswith("Float: 3.14")


def test_resolve_random_choice(monkeypatch):
    # Patch random.choice to always return 'foo'
    monkeypatch.setattr("random.choice", lambda x: x[0])
    template = "Choice: {{random.choice(['foo','bar'])}}"
    context = {}
    result = resolver.resolve_template(template, context)
    assert result == "Choice: foo"


def test_resolve_random_uuid(monkeypatch):
    # Patch uuid.uuid4 to always return a fixed value
    monkeypatch.setattr(
        "uuid.uuid4", lambda: uuid.UUID("12345678-1234-5678-1234-567812345678")
    )
    template = "UUID: {{random.uuid}}"
    context = {}
    result = resolver.resolve_template(template, context)
    assert result == "UUID: 12345678-1234-5678-1234-567812345678"


def test_resolve_time_now(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 1234567890)
    template = "Now: {{time.now}}"
    context = {}
    result = resolver.resolve_template(template, context)
    assert result == "Now: 1234567890"


def test_resolve_time_iso(monkeypatch):
    class FakeDatetime:
        @classmethod
        def now(cls, tz=None):
            class Fake:
                def isoformat(self):
                    return "2025-07-07T12:34:56+00:00"

            return Fake()

    monkeypatch.setattr("trace_generator.resolver.datetime", FakeDatetime)
    template = "Time: {{time.iso}}"
    context = {}
    result = resolver.resolve_template(template, context)
    assert result.startswith("Time: 2025-07-07T12:34:56")


def test_resolve_user_agent(monkeypatch):
    monkeypatch.setattr("random.choice", lambda x: x[-1])
    template = "UA: {{random.user_agent}}"
    context = {}
    result = resolver.resolve_template(template, context)
    assert result.startswith("UA: Mozilla/5.0 (Linux; Android 10;")


def test_resolve_last_match(monkeypatch):
    # Patch random.randint to always return 99
    monkeypatch.setattr("random.randint", lambda a, b: 99)
    template = "{{random.int(1,100)}}-{{last_match}}"
    context = {}
    result = resolver.resolve_template(template, context)
    assert result == "99-99"


def test_resolve_nested_context():
    template = "ID: {{parent.attributes.id}}"
    context = {"parent.attributes.id": 123}
    result = resolver.resolve_template(template, context)
    assert result == "ID: 123"


def test_resolve_missing_context_key(caplog):
    template = "Missing: {{not_in_context}}"
    context = {"foo": "bar"}
    caplog.set_level("WARNING")
    result = resolver.resolve_template(template, context)
    assert "Missing: {{not_in_context}}" in result
    assert "Template key not found" in caplog.text
