# Makefile for OpenTelemetry Trace Generator

.PHONY: help install run run-inmemory docker-up docker-up-inmemory docker-down docker-logs docker-clean clickhouse-shell lint lint-fix format clean test coverage

# Default target
help:
	@echo "Available targets:"
	@echo "  install          - Install Python dependencies"
	@echo "  run              - Run locally with ClickHouse (requires local setup)"
	@echo "  run-inmemory     - Run locally with in-memory database (no external deps)"
	@echo "  docker-up        - Start full stack with Docker Compose (ClickHouse)"
	@echo "  docker-up-inmemory - Start with in-memory database (no external database)"
	@echo "  docker-down      - Stop all Docker services"
	@echo "  docker-logs      - Follow logs from all services"
	@echo "  docker-clean     - Clean up Docker containers and volumes"
	@echo "  clickhouse-shell - Open ClickHouse SQL shell"
	@echo "  lint             - Lint Python code with ruff"
	@echo "  lint-fix         - Auto-fix Python code issues with ruff"
	@echo "  format           - Format Python code with ruff"
	@echo "  clean            - Remove Python artifacts and virtual environment"
	@echo "  test             - Run tests"
	@echo "  coverage          - Generate HTML coverage report"

# Python environment setup
install:
	@if [ ! -d "venv" ]; then \
		python3 -m venv venv; \
	fi
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt

# Local development - ClickHouse mode
run: install
	@echo "Starting trace generator with ClickHouse database..."
	@echo "Make sure ClickHouse is running and accessible"
	PYTHONPATH=src ./venv/bin/python -m trace_generator.main

# Detect docker compose command
DOCKER_COMPOSE := $(shell command -v docker-compose >/dev/null 2>&1 && echo docker-compose || (command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 && echo 'docker compose'))

# Docker Compose - Full stack with ClickHouse
docker-up:
	@echo "Starting full stack with ClickHouse database..."
	$(DOCKER_COMPOSE) -f docker-compose/docker-compose.yaml up --build -d
	@echo ""
	@echo "🔭 Services started successfully!"
	@echo "   UI:         http://localhost:8000"
	@echo "   Jaeger:     http://localhost:16686"
	@echo "   ClickHouse: http://localhost:8123"
	@echo ""
	@echo "Use 'make docker-logs' to follow logs"

# Docker Compose - In-memory database mode
docker-up-inmemory:
	@echo "Starting trace generator with in-memory database..."
	$(DOCKER_COMPOSE) -f docker-compose/docker-compose.inmemory.yaml up --build -d
	@echo ""
	@echo "🔭 Trace Generator started with in-memory database!"
	@echo "   UI: http://localhost:8000"
	@echo ""
	@echo "Note: Traces are stored in memory only (no persistence)"
	@echo "Use 'make docker-logs' to follow logs"

# Docker management
docker-down:
	@echo "Stopping all services..."
	$(DOCKER_COMPOSE) -f docker-compose/docker-compose.yaml down
	$(DOCKER_COMPOSE) -f docker-compose/docker-compose.yaml -f docker-compose/docker-compose.inmemory.yaml down

docker-logs:
	$(DOCKER_COMPOSE) -f docker-compose/docker-compose.yaml logs -f

docker-clean: docker-down
	@echo "Cleaning up Docker containers and volumes..."
	$(DOCKER_COMPOSE) -f docker-compose/docker-compose.yaml down -v --remove-orphans
	docker system prune -f
	@echo "Docker cleanup complete"

# Database access
clickhouse-shell:
	@echo "Opening ClickHouse shell..."
	@echo "Use SQL commands to query the otel.otel_traces table"
	@echo "Example: SELECT ServiceName, COUNT(*) FROM otel_traces GROUP BY ServiceName;"
	@echo ""
	docker exec -it $$( $(DOCKER_COMPOSE) ps -q clickhouse) clickhouse-client \
		--host localhost \
		--port 9000 \
		--user user \
		--password password \
		--database otel

# Code quality
lint: install
	@echo "Linting Python code..."
	@if [ -d "venv" ]; then \
		if ! ./venv/bin/python -m ruff --version >/dev/null 2>&1; then \
			./venv/bin/pip install ruff; \
		fi; \
		./venv/bin/python -m ruff check . ; \
	else \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi

lint-fix: install
	@echo "Auto-fixing Python code with ruff..."
	@if [ -d "venv" ]; then \
		if ! ./venv/bin/python -m ruff --version >/dev/null 2>&1; then \
			./venv/bin/pip install ruff; \
		fi; \
		./venv/bin/python -m ruff check . --fix ; \
		echo "Auto-fixes applied. Run 'make lint' to see remaining issues."; \
	else \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi

format: install
	@echo "Formatting Python code..."
	@if [ -d "venv" ]; then \
		if ! ./venv/bin/python -m ruff --version >/dev/null 2>&1; then \
			./venv/bin/pip install ruff; \
		fi; \
		./venv/bin/python -m ruff format . ; \
	else \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi

# Testing
# Ensure venv and requirements are always up to date before running tests

test: install
	@echo "Running tests with coverage..."
	@if [ -d "venv" ]; then \
		PYTHONPATH=src ./venv/bin/python -m pytest --cov=trace_generator --cov-report=term-missing tests/ -v ; \
	else \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi

coverage: install
	@echo "Generating full HTML coverage report..."
	@if [ -d "venv" ]; then \
		PYTHONPATH=src ./venv/bin/python -m pytest --cov=trace_generator --cov-report=html --cov-report=term-missing tests/ -v ; \
		if [ -d "htmlcov" ]; then \
			echo "Open htmlcov/index.html in your browser to view the detailed coverage report."; \
		fi \
	else \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi

# Cleanup
clean:
	@echo "Cleaning up Python artifacts..."
	rm -rf venv/
	rm -rf __pycache__/
	rm -rf *.pyc
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo "Cleanup complete"

# Development helpers
dev-status:
	@echo "=== Development Environment Status ==="
	@echo ""
	@echo "Python Virtual Environment:"
	@if [ -d "venv" ]; then \
		echo "Success Virtual environment exists"; \
		echo "Location: ./venv/"; \
	else \
		echo "  [ERROR]: Virtual environment not found (run 'make install')"; \
	fi
	@echo ""
	@echo "Docker Services:"
	@if [ -n "$(DOCKER_COMPOSE)" ]; then \
		echo "Success Docker Compose available"; \
		$(DOCKER_COMPOSE) ps 2>/dev/null || echo "  [ERROR]: No services currently running"; \
	else \
		echo "  [ERROR]: Docker Compose not found"; \
	fi
	@echo ""
	@echo "Available Commands:"
	@echo "  make run-inmemory    - Fastest way to start (no dependencies)"
	@echo "  make docker-up       - Full stack with ClickHouse"
	@echo "  make docker-up-inmemory - Docker with in-memory database"

# Quick development workflow
dev-quick: run-inmemory

# Full development setup
dev-full: install docker-up

# Configuration validation
validate-config:
	@echo "Validating scenarios configuration..."
	@if [ -d "venv" ]; then \
		./venv/bin/python -c "import yaml; import sys; from validation import SchemaValidator; \
		config = yaml.safe_load(open('scenarios.yaml')); \
		errors = SchemaValidator.validate_scenarios_config(config); \
		print('✅ Configuration valid') if not errors else [print(f'❌ {error}') for error in errors] or sys.exit(1)"; \
	else \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi

# Show current configuration
show-config:
	@echo "=== Current Configuration ==="
	@echo "DATABASE_TYPE: $${DATABASE_TYPE:-auto-detect}"
	@echo "DATABASE_HOST: $${DATABASE_HOST:-$${CLICKHOUSE_HOST:-not set}}"
	@echo "DATABASE_PORT: $${DATABASE_PORT:-$${CLICKHOUSE_PORT:-8123}}"
	@echo "INMEMORY_MAX_TRACES: $${INMEMORY_MAX_TRACES:-100}"
	@echo "OTEL_EXPORTER_OTLP_ENDPOINT: $${OTEL_EXPORTER_OTLP_ENDPOINT:-http://otel-collector:4317}"
	@echo ""
	@if [ -d "scenarios" ]; then \
		count=$$(find scenarios -maxdepth 1 -type f -name "*.yaml" | wc -l); \
		if [ "$$count" -gt 0 ]; then \
			echo "Scenarios directory: Success scenarios/ found with $$count YAML file(s)"; \
			echo "Files:"; \
			find scenarios -maxdepth 1 -type f -name "*.yaml" -exec echo "  - {}" \; ; \
		else \
			echo "Scenarios directory: scenarios/ found but no YAML files present"; \
		fi \
	else \
		echo "Scenarios directory: [ERROR] scenarios/ missing"; \
	fi