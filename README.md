# OpenTelemetry Trace Generator

A tool for generating realistic OpenTelemetry traces for testing and development purposes.
This project simulates various scenarios with configurable error rates, realistic timing, and nested service calls. This is made possible with the scenarios defined in the `scenarios/` directory.

**Primary Use Case:** To wire into a project to generate realistic traces that can be used for testing observability tools, dashboards, and alerting systems.

## Quick Start

### Prequisites
- Docker and Docker Compose installed

Get up and running with the OpenTelemetry Trace Generator in just a few steps.

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/trace-generator.git
cd trace-generator
```

### 2. Start with In-Memory Database (Recommended for Development)

No external dependencies required—just run:

```bash
make docker-up-inmemory
```

Or, to customize the in-memory settings. These are how many traces will be stored in memory
after which the oldest traces will be discarded:

```bash
export INMEMORY_MAX_TRACES=200
make docker-up-inmemory
```

### 3. Start with ClickHouse (Recommended for Realistic Testing)

Ensure you have a running ClickHouse instance, then configure the environment:

```bash
export DATABASE_TYPE=clickhouse
export DATABASE_HOST=your-clickhouse-host
export DATABASE_PORT=8123
export DATABASE_USER=user
export DATABASE_PASSWORD=password
export DATABASE_NAME=your_database_name
make run
```

### 4. Using Docker Compose

For a full stack (trace generator, OpenTelemetry Collector, database, and Jaeger UI):

- **In-Memory Mode**:
    ```bash
    make docker-up-inmemory
    ```
- **ClickHouse Mode** (includes Jaeger for full trace visualization):
    ```bash
    make docker-up
    ```

You can override the default settings by setting environment variables before running docker-compose:

```bash
# Database settings
export DATABASE_TYPE=clickhouse
export DATABASE_HOST=custom-clickhouse-host
export DATABASE_PORT=8123
export DATABASE_USER=custom-user
export DATABASE_PASSWORD=custom-password
export DATABASE_NAME=custom-database
export INMEMORY_MAX_TRACES=200  # Only used with in-memory database

# Other settings
export TRACE_INTERVAL_MIN=0.5    # Minimum interval in seconds between traces (0.5 = one trace every 0.5-2.0 seconds)
export TRACE_INTERVAL_MAX=2.0    # Maximum interval in seconds between traces
export TRACE_NUM_WORKERS=4       # Number of concurrent trace generation threads

make docker-up
```

### 5. Access the UI

Once running, you can access:

- **Trace Generator UI**: [http://localhost:8000](http://localhost:8000) - Built-in UI for viewing generated traces
- **Jaeger UI** (full stack only): [http://localhost:16686](http://localhost:16686) - Complete trace visualization with timeline, dependencies, and detailed span analysis

The built-in UI provides a simple interface for browsing generated traces, while Jaeger offers comprehensive trace analysis tools including trace timelines, service dependency graphs, and detailed span information.

## Full Stack Components

When you run `make docker-up`, the following services are started:

1. **Trace Generator** (port 8000) - The main application that generates traces based on your scenarios
2. **OpenTelemetry Collector** (ports 4317/4318) - Receives traces and forwards them to storage backends
3. **ClickHouse Database** (ports 8123/9000) - Persistent storage for trace data with powerful analytical capabilities
4. **Jaeger All-in-One** (port 16686) - Complete trace visualization platform with:
   - **Trace Timeline View**: See the complete flow of requests across services
   - **Service Dependency Graph**: Visualize how your services interact
   - **Span Details**: Examine individual operations, their duration, and metadata
   - **Error Analysis**: Quickly identify and analyze failed traces
   - **Performance Insights**: Analyze latency patterns and bottlenecks

The in-memory mode (`make docker-up-inmemory`) runs a lighter stack without ClickHouse or Jaeger, suitable for development and testing.

---

# Creating a Custom Scenario

First, add your service name to the `_base.yaml` file under the `services` section. Then, create a new scenario YAML file in the `scenarios/` directory.

For instance you can put in service-foo as the service name in `_base.yaml`

Below is an example of a custom scenario file (`scenarios/service_foo.yaml`):

```yaml
# scenarios/service_foo.yaml

scenario_name: "Service Foo Scenario"
description: "Generates traces for the service-foo calling the already existing user-service."
steps:
  - service: "service-foo"
    operation: "GET /api/v1/foo/{{user_id}}"
    kind: "CLIENT"
    delay_ms: [10, 50]  # Simulate network delay
    attributes:
      user_id: "{{random.int(1000, 9999)}}"
      session_id: "sess-{{random.uuid}}"

  - service: "user-service"
    operation: "POST /api/v1/users/{{user_id}}/foo"
    kind: "SERVER"
    delay_ms: [20, 100]
    attributes:
      user_id: "{{user_id}}"
      client_ip: "{{random.ipv4}}"
```

## Extended Example: E-commerce Order Processing with Error Simulation

Here's a more comprehensive example that demonstrates error conditions, realistic timing, and nested service calls (`scenarios/ecommerce_order.yaml`):

```yaml
# scenarios/ecommerce_order.yaml
scenario_name: "E-commerce Order Processing"
description: "Simulates a complete order flow with realistic error rates and timing"
weight: 15
vars:
  user_id: "{{random.int(1000, 9999)}}"
  order_id: "order-{{random.uuid}}"
  item_id: "{{random.int(100, 999)}}"
root_span:
  service: "api-gateway"
  operation: "POST /api/v1/orders"
  kind: "SERVER"
  delay_ms: [5, 15]                    # Fast API response
  attributes:
    http.method: "POST"
    user.id: "{{user_id}}"
    order.id: "{{order_id}}"
  error_conditions:
    - probability: 2                   # 2% rate limiting
      type: "RateLimitExceeded"
      message: "API rate limit exceeded for user."
  calls:
    # User authentication and validation
    - service: "auth-service"
      operation: "validate_user_session"
      kind: "CLIENT"
      delay_ms: [10, 30]               # Fast auth check
      attributes:
        user.id: "{{parent.attributes.user.id}}"
      error_conditions:
        - probability: 5               # 5% auth failures
          type: "InvalidSession"
          message: "User session is invalid or expired."
        - probability: 1               # 1% service down
          type: "AuthServiceDown"
          message: "Authentication service is unavailable."
      calls:
        # Inventory check with realistic database timing
        - service: "inventory-service"
          operation: "check_item_availability"
          kind: "CLIENT"
          delay_ms: [20, 80]           # Database query timing
          attributes:
            item.id: "{{item_id}}"
            db.system: "postgresql"
          error_conditions:
            - probability: 8           # 8% out of stock (realistic)
              type: "OutOfStock"
              message: "Requested item is out of stock."
            - probability: 3           # 3% database timeouts
              type: "DatabaseTimeout"
              message: "Inventory database query timed out."
          calls:
            # Payment processing - slower with higher error rates
            - service: "payment-service"
              operation: "process_payment"
              kind: "CLIENT"
              delay_ms: [200, 500]     # Payment gateway delays
              attributes:
                payment.amount: "{{random.float(10.00, 500.00)}}"
                payment.method: "credit_card"
              error_conditions:
                - probability: 10      # 10% payment declines
                  type: "PaymentDeclined"
                  message: "Payment was declined by the bank."
                - probability: 3       # 3% fraud detection
                  type: "FraudDetected"
                  message: "Transaction flagged as fraudulent."
                - probability: 2       # 2% gateway timeouts
                  type: "PaymentTimeout"
                  message: "Payment gateway timed out."
              calls:
                # Order fulfillment
                - service: "fulfillment-service"
                  operation: "create_shipment"
                  kind: "CLIENT"
                  delay_ms: [50, 150]  # Shipping label generation
                  attributes:
                    order.id: "{{order_id}}"
                    shipping.method: "standard"
                  error_conditions:
                    - probability: 4   # 4% fulfillment issues
                      type: "FulfillmentFailed"
                      message: "Unable to create shipment for order."
                  calls:
                    # Notification delivery
                    - service: "notification-service"
                      operation: "send_order_confirmation"
                      kind: "CLIENT"
                      delay_ms: [30, 80]
                      attributes:
                        notification.type: "email"
                        user.id: "{{user_id}}"
                      error_conditions:
                        - probability: 6  # 6% email delivery issues
                          type: "EmailDeliveryFailed"
                          message: "Failed to send order confirmation email."
```

**Key Features Demonstrated:**

- **Error Probability**: Use whole numbers 0-100 representing percentage chance (e.g., `probability: 5` = 5% failure rate)
- **Realistic Timing**: `delay_ms: [min, max]` simulates real-world service response times
  - `[5, 15]` = Fast API responses
  - `[200, 500]` = Payment gateway delays  
  - `[20, 80]` = Database query timing
- **Nested Service Calls**: Creates realistic microservice interaction patterns with deep call stacks
- **Error Types**: Specific error conditions with meaningful messages that reflect real operational issues
- **Variable Propagation**: Parent attributes flow down to child spans using `{{parent.attributes.field}}`

The generator will create traces that follow this flow, with the specified error rates and timing characteristics, giving you realistic observability data for testing dashboards and alerting systems.

**How it works:**
- Each `step` defines a service, operation, optional attributes, and simulated duration.
- The scenario will generate traces that follow the defined sequence.
- You can add as many steps and attributes as needed to model your workflow.

After creating your scenario file, you can run the trace generator with your custom scenario as long as it is in the `scenarios/` directory. The trace generator will automatically pick it up and generate traces based on the defined steps.

## Architecture Overview

### Database Architecture

The trace generator uses an abstracted database layer that enables seamless switching between different storage backends.

#### DatabaseInterface

The core of the database abstraction is the `DatabaseInterface` abstract base class, which defines the contract that all database implementations must follow:

```python
class DatabaseInterface(ABC):
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the database. Returns True if successful."""
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close database connection."""
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check if the database is healthy and responsive."""
    
    @abstractmethod
    def fetch_unique_traces(self, limit: int) -> List[Dict[str, Any]]:
        """Fetch unique traces from the database."""
    
    @abstractmethod
    def get_trace_counts(self) -> Dict[str, int]:
        """Get trace count statistics."""
    
    @abstractmethod
    def get_service_names(self) -> List[str]:
        """Get list of service names from stored traces."""
    
    @abstractmethod
    def add_trace(self, trace: Dict[str, Any]) -> None:
        """Add a trace to the database (for in-memory and testing)."""
```

#### Implementations

Two concrete implementations are provided:

1. **ClickHouseDatabase**: Connects to a ClickHouse database for production use
   - High-performance storage for large trace volumes
   - Persistent across restarts
   - Requires external ClickHouse instance

2. **InMemoryDatabase**: In-memory storage using a thread-safe deque
   - No external dependencies
   - Fast access and storage
   - Limited capacity (configurable via `INMEMORY_MAX_TRACES`)
   - Data lost on restart

#### Factory Function

Database instances are created using the `create_database()` factory function:

```python
# This handles automatic fallback to in-memory when needed
db = create_database(
    db_type='clickhouse',  # or 'inmemory'
    host='localhost',
    port=8123,
    user='default',
    password='password',
    database='otel'
)
```

## Running Tests and Coverage

The Makefile is designed to ensure your Python virtual environment and all dependencies are always up to date before running tests or generating coverage reports. This prevents issues with missing packages (such as `pytest-cov`) after a `make clean` or when updating `requirements.txt`.

**To run tests with coverage:**

```bash
make test
```

**To generate an HTML coverage report:**

```bash
make coverage
```

Both commands will automatically:
- Create the `venv` virtual environment if it does not exist
- Install or update all dependencies from `requirements.txt`
- Run the tests or generate the coverage report

You do not need to manually run `make install` before testing or coverage—this is handled automatically.

## Linting and Formatting

The Makefile will automatically install the `ruff` linter in your virtual environment if it is not already present when you run:

```bash
make lint
```

or

```bash
make format
```

This ensures you can always lint or format your code, even after a `make clean` or on a fresh setup. If you see lint errors, you can fix many of them automatically with:

```bash
./venv/bin/python -m ruff check . --fix
```

or for formatting:

```bash
make format
```

# Project Directory Structure

Below is an overview of the main files and directories in this repository:

```
trace-generator/
├── __init__.py                # Package marker for Python module
├── Dockerfile                 # Dockerfile for building the trace generator app (project root)
├── Makefile                   # Development and management commands
├── README.md                  # This documentation file
├── requirements.txt           # Python dependencies
├── docker-compose/            # Docker Compose and orchestration files
│   ├── docker-compose.yaml           # Docker Compose file for full stack (ClickHouse, Collector, Jaeger, UI)
│   ├── docker-compose.inmemory.yaml  # Docker Compose for in-memory mode
├── otel-collector/            # OpenTelemetry Collector container and config
│   ├── Dockerfile                     # Dockerfile for the OpenTelemetry Collector
│   ├── otel-collector-config.yaml     # Collector config (ClickHouse mode)
│   └── otel-collector-inmemory.yaml   # Collector config (in-memory mode)
├── scenarios/                 # Directory containing all trace scenario definitions
│   ├── _base.yaml                 # Shared configuration (schema version, service list)
│   ├── 01_api_gateway.yaml        # API Gateway scenario (deep call stack, auth flow)
│   ├── 02_billing_service.yaml    # Billing/payment scenario
│   ├── 03_search_service.yaml     # Search service batch indexing scenario
│   ├── 04_async_producer.yaml     # Async producer (order creation, context export)
│   ├── 05_async_consumer.yaml     # Async consumer (order processing, context import)
│   ├── 06_grafana_tempo.yaml      # Observability/Tempo query scenario
│   ├── 07_analytics_batch.yaml    # Analytics batch job scenario
│   ├── 08_user_profile_update.yaml # User profile CRUD scenario
│   ├── 09_configuration_service.yaml # Config service with error rates
│   └── 10_search_service_slow.yaml   # Search service with very slow indexing
└── src/                        # Source files for the trace generator
    └── trace_generator/        # Core Python modules for the trace generator
        ├── __init__.py                # Package marker
        ├── config.py                  # Application configuration and environment variable parsing
        ├── data.py                    # Data access and trace data service logic
        ├── database.py                # Database abstraction and implementations (ClickHouse, InMemory)
        ├── engine.py                  # Trace generation engine and OpenTelemetry integration
        ├── main.py                    # Main application entry point
        ├── resolver.py                # Variable and template resolution logic for scenarios
        ├── ui.py                      # Web UI for trace visualization
        ├── validation.py              # YAML schema validation and scenario loading
        ├── version                    # Application version string
        └── ...                        # Other module files
```

**Key Directories:**
- `src/trace_generator/`: All core Python modules for the trace generator (config, engine, database, data, resolver, validation, UI, etc.).
- `scenarios/`: All trace scenario YAML files. Each file defines one or more scenarios. The `_base.yaml` file contains shared configuration (schema version, list of all services, etc.).
- `docker-compose/`: All Docker Compose and orchestration files for running the stack in different modes.
- `otel-collector/`: All OpenTelemetry Collector Docker and configuration files.
- `tests/`: All unit and integration tests for the trace generator (mirrors the src/trace_generator/ layout).

**Key Files:**
- `src/trace_generator/main.py`: Application entry point. Loads configuration, scenarios, and starts the trace generator and UI.
- `src/trace_generator/config.py`: Handles all environment variables and configuration logic.
- `src/trace_generator/engine.py`: Core trace generation logic, including span creation and error simulation.
- `src/trace_generator/database.py`: Database abstraction and implementations for ClickHouse and in-memory storage.
- `src/trace_generator/data.py`: Data access and trace data service logic.
- `src/trace_generator/validation.py`: Loads and validates scenario YAML files.
- `src/trace_generator/ui.py`: Web UI for browsing and visualizing generated traces.
- `src/trace_generator/resolver.py`: Variable and template resolution logic for scenarios.
- `src/trace_generator/version`: Application version string.
- `Makefile`: Developer commands for running, testing, and managing the stack.
- `Dockerfile`: Containerization for the trace generator app (project root).
- `docker-compose/docker-compose.yaml` and `docker-compose/docker-compose.inmemory.yaml`: Orchestration for full stack and in-memory modes.
- `otel-collector/Dockerfile` and configs: Container and configuration for the OpenTelemetry Collector.
- `requirements.txt`: Python dependencies for the project.

See each file for more details on its specific role.
