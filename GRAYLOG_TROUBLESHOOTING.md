# Graylog Telemetry Troubleshooting Guide

## Issues Identified and Fixed

### 1. **LoggerProvider Not Properly Configured**
- **Issue**: The LoggerProvider was created but the handler wasn't properly configured to use it
- **Fix**: Ensured LoggingHandler is properly attached to the root logger with the LoggerProvider

### 2. **Endpoint Format Normalization**
- **Issue**: Endpoint might have `http://` or `https://` prefix which breaks gRPC endpoint format
- **Fix**: Added endpoint normalization to strip protocol prefixes (gRPC endpoints should be `host:port`)

### 3. **Missing Diagnostic Information**
- **Issue**: No logging when telemetry initialization fails or succeeds
- **Fix**: Added diagnostic print statements and error handling

### 4. **Global Initialization Flag Limitation**
- **Issue**: The `_TELEMETRY_INITIALIZED` flag means only the first agent to call `setup_telemetry()` actually configures telemetry
- **Current Behavior**: All agents share the same service name (whichever calls setup_telemetry first)
- **Note**: This is by design to avoid duplicate handlers, but service names will reflect the first initialization

## Environment Variables

Ensure these environment variables are set correctly:

```bash
# For Docker (points to otel-collector service)
GRAYLOG_OTLP_GRPC_ENDPOINT=otel-collector:4317

# For local development or direct connection
GRAYLOG_OTLP_GRPC_ENDPOINT=localhost:4317  # or your Graylog server IP:port

# Optional settings
GRAYLOG_INSECURE=true  # Set to false if using TLS
GRAYLOG_SERVICE_NAMESPACE=agent-codex
```

## Verification Steps

### 1. Check Environment Variables
```bash
# In Docker
docker compose exec trader-agent env | grep GRAYLOG

# Or check .env file
cat .env | grep GRAYLOG
```

### 2. Check Telemetry Initialization Logs
When the application starts, you should see:
```
[Telemetry] Initializing for service: <service-name>, endpoint: <endpoint>, namespace: <namespace>
[Telemetry] Successfully initialized telemetry for <service-name>
```

### 3. Verify Graylog Connection

#### Check if logs are reaching Graylog:
1. Access Graylog UI at `http://localhost:9000` (default: admin/admin)
2. Go to "Search" tab
3. Filter by `service.name: "orchestrator"` or your service name
4. Look for log entries

#### Check OpenTelemetry Collector logs:
```bash
docker compose logs otel-collector
```

#### Check trader-agent logs for telemetry errors:
```bash
docker compose logs trader-agent | grep -i telemetry
```

### 4. Test Logging
The telemetry system sends a test log on initialization:
- Event: `telemetry.initialized`
- Should appear in Graylog after startup

### 5. Verify Agent Execution Logs
Agent execution logs are sent via:
- `log_agent_event()` calls in agent code
- Structured events like `agent.bridge.request`, `tool.invocation`, etc.
- These should appear in Graylog with the event type in the log message

## Common Issues

### Logs Not Appearing in Graylog

1. **Wrong Endpoint Format**
   - Ensure endpoint is `host:port` (no `http://` prefix)
   - For Docker: use `otel-collector:4317`
   - For local: use `localhost:4317` or your server IP

2. **Network Connectivity**
   - In Docker: ensure `otel-collector` service is running and reachable
   - Check: `docker compose ps otel-collector`
   - Verify: `docker compose exec trader-agent ping otel-collector`

3. **Graylog Input Not Configured**
   - Graylog needs an OTLP input configured
   - Check Graylog UI → System → Inputs
   - Ensure OTLP gRPC input is running on port 4317

4. **OpenTelemetry Collector Configuration**
   - Check `observability/otel-collector-config.yaml`
   - Verify logs pipeline is configured correctly
   - Ensure `GRAYLOG_OTLP_EXPORTER_ENDPOINT` is set correctly

5. **Log Level Too High**
   - Current setting: `logging.INFO`
   - Check if agent logs are at INFO level or above
   - Lower level logs (DEBUG) won't be sent

### Service Name Not Appearing Correctly

Due to the global initialization flag, the service name reflects the first agent/service that calls `setup_telemetry()`. In the FastAPI app:
- `setup_telemetry("agent-platform")` is called in `main.py`
- Individual agents also call `setup_telemetry()` but it returns early
- Result: All logs show service name as "agent-platform"

**Workaround**: If you need distinct service names, remove or modify the global flag logic in `telemetry.py`.

## Debugging Commands

```bash
# Check all telemetry-related environment variables
docker compose exec trader-agent env | grep -E "(GRAYLOG|OTEL)"

# Check OpenTelemetry Collector status
docker compose ps otel-collector

# View collector logs
docker compose logs -f otel-collector

# View trader-agent logs with telemetry context
docker compose logs -f trader-agent | grep -E "(Telemetry|telemetry)"

# Test OTLP endpoint connectivity
docker compose exec trader-agent nc -zv otel-collector 4317

# Check Graylog container status
docker compose ps graylog

# View Graylog logs
docker compose logs -f graylog
```

## Expected Log Flow

1. Agent code calls `log_agent_event()` or uses `_LOGGER.info()`
2. Python logging captures the log
3. LoggingHandler (OpenTelemetry) processes the log
4. BatchLogRecordProcessor batches logs
5. OTLPLogExporter sends via gRPC to endpoint
6. OpenTelemetry Collector receives on port 4317
7. Collector processes and forwards to Graylog
8. Graylog indexes and stores the logs

## Additional Resources

- OpenTelemetry Python SDK: https://opentelemetry.io/docs/instrumentation/python/
- Graylog OTLP Input: https://docs.graylog.org/docs/opentelemetry
- OpenTelemetry Collector: https://opentelemetry.io/docs/collector/


