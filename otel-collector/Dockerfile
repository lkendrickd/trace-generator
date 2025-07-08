# OpenTelemetry Collector Dockerfile
FROM otel/opentelemetry-collector-contrib:0.96.0

# Copy the configuration file
COPY otel-collector/otel-collector-config.yaml /etc/otelcol-contrib/config.yaml

# Expose the necessary ports
EXPOSE 4317 4318

# Run the collector with the custom configuration
CMD ["--config=/etc/otelcol-contrib/config.yaml"]