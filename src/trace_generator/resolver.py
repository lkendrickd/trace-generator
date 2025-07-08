# resolver.py
"""
Dynamic value parser for scenario templates.
Handles {{...}} syntax resolution with support for random values, time functions,
context variables, and nested key resolution.
"""

import re
import random
import uuid
import ast
import time
import logging
from datetime import datetime, timezone
from threading import Lock, get_ident
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)


class ValueResolver:
    """
    Parses {{...}} syntax in strings to generate dynamic values.

    Supports:
    - Context variables: {{user_id}}, {{parent.attributes.id}}
    - Random values: {{random.int(1,100)}}, {{random.uuid}}, {{random.ipv4}}
    - Time functions: {{time.now}}, {{time.iso}}
    - Choice selections: {{random.choice(['option1', 'option2'])}}
    - Last match references: {{last_match}}
    - User agents: {{random.user_agent}}
    """

    def __init__(self):
        self.last_match_map = {}
        self.last_match_lock = Lock()  # Thread safety for last_match_map
        self.user_agents = [
            "curl/7.68.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Mobile Safari/537.36",
        ]

        # Pre-compile regexes for performance
        self.template_regex = re.compile(r"\{\{([\w\.]+)\}\}")
        self.random_int_regex = re.compile(r"\{\{random\.int\((\d+),\s*(\d+)\)\}\}")
        self.random_float_regex = re.compile(
            r"\{\{random\.float\(([\d\.]+),\s*([\d\.]+)\)\}\}"
        )
        self.random_choice_regex = re.compile(r"\{\{random\.choice\((.*?)\)\}\}")

    def resolve(self, value: Any, context: Dict = None) -> Any:
        """
        Resolves template variables in a value.

        Args:
            value: The value to resolve (only processes strings)
            context: Context dictionary for variable resolution

        Returns:
            Resolved value with templates replaced
        """
        if not isinstance(value, str):
            return value

        iteration_count = 0
        seen_values: Set[str] = set()
        max_iterations = getattr(self, "MAX_TEMPLATE_ITERATIONS", 10)

        while iteration_count < max_iterations:
            if value in seen_values:
                logger.warning(f"Circular reference detected in template: {value}")
                break
            seen_values.add(value)

            resolved_value = self._resolve_templates(value, context or {})
            if resolved_value == value:
                break
            value = resolved_value
            iteration_count += 1

        if iteration_count >= max_iterations:
            logger.warning(
                f"Template resolution hit max iterations ({max_iterations}): {value}"
            )

        return value

    def _resolve_templates(self, value: str, context: Dict) -> str:
        """
        Resolves templates in the correct order:
        1. Random values first (to handle templates that resolve to random expressions)
        2. Special syntax (last_match)
        3. Context variables (nested key support)
        """
        # CRITICAL: Process random values FIRST, then templates
        # This ensures that if a template resolves to {{random.uuid}}, it gets processed
        value = self._resolve_random_values(value)
        value = self._resolve_special_syntax(value)

        # Handle nested keys like 'parent.attributes.id'
        for match in self.template_regex.finditer(value):
            key_path = match.group(1).split(".")
            original_template = match.group(0)

            # Greedy traversal logic to handle keys with dots
            current_level = context
            remaining_path = key_path[:]

            while remaining_path:
                found_match = False
                # Try to match the longest possible key first
                for i in range(len(remaining_path), 0, -1):
                    potential_key = ".".join(remaining_path[:i])
                    if (
                        isinstance(current_level, dict)
                        and potential_key in current_level
                    ):
                        current_level = current_level[potential_key]
                        remaining_path = remaining_path[i:]
                        found_match = True
                        break
                if not found_match:
                    current_level = None
                    break

            if current_level is not None:
                value = value.replace(original_template, str(current_level), 1)
            else:
                # Log warning for missing template keys to aid debugging
                logger.warning(
                    f"Template key not found: '{original_template}' - available context keys: {list(context.keys())}"
                )

        return value

    def _resolve_special_syntax(self, value: str) -> str:
        """Resolves special template syntax like {{last_match}}"""
        if "{{last_match}}" in value:
            thread_id = get_ident()
            with self.last_match_lock:  # Thread-safe access
                last_val = self.last_match_map.get(thread_id, "")
            value = value.replace("{{last_match}}", str(last_val))
        return value

    def _resolve_random_values(self, value: str) -> str:
        """
        Resolves all random value templates.
        Processes in specific order to handle dependencies.
        """
        # Random integers with last_match tracking
        for match in self.random_int_regex.finditer(value):
            min_val, max_val = map(int, match.groups())
            rand_val = str(random.randint(min_val, max_val))
            thread_id = get_ident()
            with self.last_match_lock:  # Thread-safe access
                self.last_match_map[thread_id] = rand_val
            value = value.replace(match.group(0), rand_val, 1)

        # Random floats
        for match in self.random_float_regex.finditer(value):
            min_val, max_val = map(float, match.groups())
            rand_val = f"{random.uniform(min_val, max_val):.2f}"
            value = value.replace(match.group(0), rand_val, 1)

        # Random choice from list
        for match in self.random_choice_regex.finditer(value):
            try:
                choices = ast.literal_eval(match.group(1))
                if isinstance(choices, list):
                    value = value.replace(match.group(0), random.choice(choices), 1)
            except (ValueError, SyntaxError):
                logger.warning(
                    f"Could not parse choices for random.choice: {match.group(1)}"
                )

        # Simple string replacements
        replacements = {
            "{{random.uuid}}": lambda: str(uuid.uuid4()),
            "{{random.ipv4}}": lambda: f"{random.randint(1, 254)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}",
            "{{random.user_agent}}": lambda: random.choice(self.user_agents),
            "{{time.now}}": lambda: str(int(time.time())),
            "{{time.iso}}": lambda: datetime.now(timezone.utc).isoformat(),
        }

        for placeholder, generator in replacements.items():
            if placeholder in value:
                value = value.replace(placeholder, generator())

        return value


# Backwards compatibility and convenience functions
def resolve_value(value: Any, context: Dict = None) -> Any:
    """Convenience function for one-off value resolution"""
    resolver = ValueResolver()
    return resolver.resolve(value, context)


def create_resolver() -> ValueResolver:
    """Factory function for creating a new resolver instance"""
    return ValueResolver()


def resolve_template(template, context):
    """Convenience function for template resolution, for test and API compatibility."""
    return ValueResolver().resolve(template, context)
