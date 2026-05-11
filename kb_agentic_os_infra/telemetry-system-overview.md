# Monitoring - Telemetry System

Direct RabbitMQ telemetry for tracking agent interactions and LLM calls.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  APPLICATION (Python)                        │
├─────────────────────────────────────────────────────────────┤
│  Agent Code                                                  │
│    ├─> log_llm_interaction()  [llm_telemetry.py]            │
│    ├─> log_a2a_interaction()  [a2a_telemetry.py]            │
│    └─> log_mcp_call()         [mcp_telemetry.py]            │
│                          ▼                                   │
│  ┌───────────────────────────────────────────┐              │
│  │ TelemetryClient (Singleton)               │              │
│  │  • Direct send to RabbitMQ                │              │
│  │  • Level filtering (DEBUG → CRITICAL)     │              │
│  │  • Auto-reconnect on failure              │              │
│  └───────────────────┬───────────────────────┘              │
└──────────────────────┼──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    RABBITMQ                                  │
├─────────────────────────────────────────────────────────────┤
│  Exchange: agent-logs (topic, durable)                      │
│  Queues:                                                     │
│    • logstash-llm     ← agent.llm                           │
│    • logstash-a2a     ← agent.a2a                           │
│    • logstash-mcp     ← agent.mcp                           │
│    • logstash-generic ← agent.generic                       │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    LOGSTASH                                  │
├─────────────────────────────────────────────────────────────┤
│  Consumes from 4 queues → dynamic ES index by kind          │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  ELASTICSEARCH                               │
├─────────────────────────────────────────────────────────────┤
│  Indices: agent-llm-YYYY.MM, agent-a2a-YYYY.MM, etc.        │
│  ILM: 60-day retention                                      │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    GRAFANA                                   │
│  Dashboards & visualization at http://localhost:3000        │
└─────────────────────────────────────────────────────────────┘
```

## Components

### `telemetry.py`
**TelemetryClient** (Singleton)
- Single RabbitMQ connection per process
- Direct `basic_publish()` on each log call
- Level filtering (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Thread-safe with connection lock
- Auto-reconnect on connection loss

### `llm_telemetry.py`
Logs LLM interactions with token usage, latency, and costs.

### `a2a_telemetry.py`
Logs agent-to-agent communication with request/response payloads.

### `mcp_telemetry.py`
Logs MCP tool calls with latency and response preview.

## Configuration

```bash
RABBITMQ_ENABLED=true              # Enable/disable telemetry
RABBITMQ_HOSTS=illin4436:5672      # RabbitMQ host(s)
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_EXCHANGE=agent-logs
RABBITMQ_ROUTING_PREFIX=agent
LOG_LEVEL=INFO                     # DEBUG|INFO|WARNING|ERROR|CRITICAL
```

## Usage

### Direct Telemetry
```python
from agentic_os_infra.core.monitoring.telemetry import get_client

client = get_client()
client.info("Operation completed", extra={"_event": {"key": "value"}})
client.error("Something failed", exc_info=True)
```

### LLM Telemetry
```python
from agentic_os_infra.core.monitoring.llm_telemetry import log_llm_interaction

log_llm_interaction(
    ai_obj=response,
    llm_latency_seconds=1.23,
    model_provider="azure_openai",
    framework="langchain",
    temperature=0.7,
    llm_version="gpt-4",
    model_name="gpt-4-turbo",
    monitoring_metadata={"agent_id": "...", "session_id": "..."}
)
```

### A2A Telemetry
```python
from agentic_os_infra.core.monitoring.a2a_telemetry import log_a2a_interaction

log_a2a_interaction(
    direction="outgoing",
    from_="agent-1",
    to="agent-2",
    request_payload={"task": "analyze"},
    response_payload={"result": "..."},
    latency_seconds=0.5,
    monitoring_metadata={"agent_id": "..."}
)
```

### MCP Telemetry
```python
from agentic_os_infra.core.monitoring.mcp_telemetry import log_mcp_call

log_mcp_call(
    tool_name="file_search",
    latency_seconds=0.8,
    response_preview="Found 5 files...",
    monitoring_metadata={"agent_id": "..."}
)
```

## Event Schema

```json
{
  "timestamp_created": "2024-11-29T12:00:00.000Z",
  "message": "Event description",
  "level": "info",
  "host": "hostname",
  "PID": 12345,
  "kind": "llm|a2a|mcp|generic",
  "session_id": "uuid",
  "agent_id": "uuid",
  ...
}
```

## Deployment

```bash
cd monitoring-infrastructure
docker-compose up -d
```

**Service URLs:**
- RabbitMQ: http://localhost:15672 (guest/guest)
- Elasticsearch: http://localhost:9200 (elastic/elastic123)
- Grafana: http://localhost:3000 (admin/admin)
