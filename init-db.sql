CREATE DATABASE IF NOT EXISTS otel;

-- Updated schema compatible with OpenTelemetry Collector 0.114.0
CREATE TABLE IF NOT EXISTS otel.otel_traces (
    Timestamp DateTime64(9) CODEC(Delta, ZSTD),
    TraceId String CODEC(ZSTD),
    SpanId String CODEC(ZSTD),
    ParentSpanId String CODEC(ZSTD),
    TraceState String CODEC(ZSTD),
    SpanName LowCardinality(String) CODEC(ZSTD),
    SpanKind LowCardinality(String) CODEC(ZSTD),
    ServiceName LowCardinality(String) CODEC(ZSTD),
    ServiceVersion String CODEC(ZSTD),
    ResourceAttributes Map(LowCardinality(String), String) CODEC(ZSTD),
    ScopeName String CODEC(ZSTD),
    ScopeVersion String CODEC(ZSTD),
    ScopeAttributes Map(LowCardinality(String), String) CODEC(ZSTD),
    SpanAttributes Map(LowCardinality(String), String) CODEC(ZSTD),
    Duration Int64 CODEC(ZSTD),
    StatusCode LowCardinality(String) CODEC(ZSTD),
    StatusMessage String CODEC(ZSTD),
    Events Nested (
        Timestamp DateTime64(9),
        Name LowCardinality(String),
        Attributes Map(LowCardinality(String), String)
    ) CODEC(ZSTD),
    Links Nested (
        TraceId String,
        SpanId String,
        TraceState String,
        Attributes Map(LowCardinality(String), String)
    ) CODEC(ZSTD)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(Timestamp)
ORDER BY (ServiceName, SpanName, toStartOfHour(Timestamp), TraceId)
TTL toDateTime(Timestamp) + INTERVAL 72 HOUR
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;CREATE DATABASE IF NOT EXISTS otel;

-- Default schema for OpenTelemetry traces as expected by the ClickHouse exporter
CREATE TABLE IF NOT EXISTS otel.otel_traces (
    Timestamp DateTime64(9) CODEC(Delta, ZSTD),
    TraceId String CODEC(ZSTD),
    SpanId String CODEC(ZSTD),
    ParentSpanId String CODEC(ZSTD),
    TraceState String CODEC(ZSTD),
    SpanName LowCardinality(String) CODEC(ZSTD),
    SpanKind LowCardinality(String) CODEC(ZSTD),
    ServiceName LowCardinality(String) CODEC(ZSTD),
    ServiceVersion String CODEC(ZSTD),
    ResourceAttributes Map(LowCardinality(String), String) CODEC(ZSTD),
    ScopeAttributes Map(LowCardinality(String), String) CODEC(ZSTD),
    SpanAttributes Map(LowCardinality(String), String) CODEC(ZSTD),
    Duration Int64 CODEC(ZSTD),
    StatusCode LowCardinality(String) CODEC(ZSTD),
    StatusMessage String CODEC(ZSTD),
    Events Nested (
        Timestamp DateTime64(9),
        Name LowCardinality(String),
        Attributes Map(LowCardinality(String), String)
    ) CODEC(ZSTD),
    Links Nested (
        TraceId String,
        SpanId String,
        TraceState String,
        Attributes Map(LowCardinality(String), String)
    ) CODEC(ZSTD)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(Timestamp)
ORDER BY (ServiceName, SpanName, toStartOfHour(Timestamp), TraceId)
TTL toDateTime(Timestamp) + INTERVAL 72 HOUR
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;