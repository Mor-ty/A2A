# Telemetry Guide for External Teams

If your division uses this package and wants to log custom events, exceptions, or domain-specific telemetry, use the generic telemetry client.

## The `kind` Field

Always use `kind: "generic"` for your custom events. This routes your telemetry to the `agent-generic` Kafka topic and `agent-generic-YYYY.MM` Elasticsearch index.

> **Note**: LLM interactions, MCP tool calls, and agent-to-agent communication are automatically handled by wrappers (`llm_telemetry.py`, `mcp_telemetry.py`, `a2a_telemetry.py`). You don't need to log these manually - they are captured automatically when you use the framework's integrations.

## Using the Built-in Wrappers

The framework provides wrappers that automatically capture telemetry. Simply use these wrappers in your agent code - no manual logging required.

### MCP Wrapper (Tool Calls)

```python
# List available tools - telemetry captured automatically
tools = await self.mcp_wrapper.list_tools()

# Call a tool - telemetry captured automatically (duration, success/failure, arguments, etc.)
tool_result = await self.mcp_wrapper.call_tool(tool_name, arguments)
```

### LLM Adapter (Chat Completions)

```python
# Make an LLM call - telemetry captured automatically (tokens, latency, model, etc.)
response = await self.llm_adapter.llm_chat(messages)
```

These wrappers emit structured telemetry events with all relevant fields (`kind: "llm"`, `kind: "mcp"`) routed to their respective Kafka topics and Elasticsearch indices.

## Basic Setup

```python
from agentic_os_infra.core.monitoring.telemetry import get_client

# Get the singleton telemetry client (same instance across your application)
client = get_client()
```

Your agent should already have a `monitoring_metadata` dict containing all observability context (agent_id, session_id, execution_id, etc.). You don't need to manage these fields yourself - just spread them into your events.

## Logging Custom Events

Use the appropriate log level method with `**monitoring_metadata` spread into the event via `extra={"_event": {"kind": "generic", **monitoring_metadata, ...}}`:

```python
# INFO level - general events
client.info("Payment processed successfully", extra={"_event": {
    "kind": "generic",
    **monitoring_metadata,
    "payment_id": "pay_12345",
    "amount": 99.99,
    "currency": "USD",
    "processor": "stripe"
}})

# WARNING level - potential issues (as used in agent_executor.py)
client.warning("Custom Guardrails check failed. Returning early.", 
               extra={"_event": {"kind": "generic", **monitoring_metadata}})

# DEBUG level - verbose diagnostic info (filtered by LOG_LEVEL env var)
client.debug("Cache lookup", extra={"_event": {
    "kind": "generic",
    **monitoring_metadata,
    "cache_key": "user:123",
    "hit": True
}})

```

## Logging Exceptions

Use `error()` or `critical()` with `exc_info=True` to automatically capture exception details (`error.type` and `error.message` fields are added automatically):

```python
try:
    result = external_api.call()
except TimeoutError as e:
    client.error("External API timeout", exc_info=True, extra={"_event": {
        "kind": "generic",
        **monitoring_metadata,
        "api_name": "inventory-service",
        "timeout_seconds": 30
    }})
    # Continues execution - telemetry is non-blocking

except Exception as e:
    client.critical("Unrecoverable error in pipeline", exc_info=True, extra={"_event": {
        "kind": "generic",
        **monitoring_metadata,
        "pipeline_stage": "transform",
        "input_record_id": "rec_456"
    }})
    raise  # Re-raise after logging
```

## The monitoring_metadata Dict

The `monitoring_metadata` dict is maintained by your agent and contains all standard observability fields. You don't need to construct or modify it - just spread it into your events with `**monitoring_metadata`.

**Fields included in monitoring_metadata:**

| Field | Description |
|-------|-------------|
| `agent_id` | Unique identifier for your agent |
| `agent_name` | Human-readable agent name |
| `session_id` | Session/conversation identifier |
| `execution_id` | Specific execution/run identifier |
| `experience_id` | User experience/flow identifier |
| `skill_id` | Current skill/capability identifier |
| `skill_name` | Human-readable skill name |
| `context_id` | Context/state identifier |
| `task_id` | Current task identifier |
| `location` | Service/deployment location |

**Example with domain-specific fields:**

```python
client.info("Order fulfilled", extra={"_event": {
    "kind": "generic",
    **monitoring_metadata,  # Spreads all observability fields automatically
    
    # Your domain-specific fields
    "order_id": "ORD-12345",
    "warehouse": "US-WEST-2",
    "items_count": 3,
    "shipping_method": "express",
    "estimated_delivery": "2024-12-05"
}})
```

## Best Practices

1. **Use structured data**: Pass typed values (numbers, booleans) instead of embedding them in strings
   ```python
   # Good
   extra={"_event": {"kind": "generic", **monitoring_metadata, "latency_ms": 150, "success": True}}
   
   # Avoid
   extra={"_event": {"kind": "generic", **monitoring_metadata, "message": "latency was 150ms, success=true"}}
   ```

2. **Choose appropriate log levels**:
   - `DEBUG` - Verbose diagnostics (filtered in production)
   - `INFO` - Normal operations, business events
   - `WARNING` - Degraded performance, retries, recoverable issues
   - `ERROR` - Failures that are handled but need attention
   - `CRITICAL` - System failures requiring immediate action

3. **Always spread monitoring_metadata**: Include `**monitoring_metadata` in every event for consistent correlation across services

4. **Keep events atomic**: Log one event per operation rather than batching multiple operations

5. **Avoid sensitive data**: Do not log PII, credentials, or sensitive business data

## Viewing Your Events

Your custom events are stored in the `agent-generic-*` Elasticsearch index and can be viewed through **Grafana** dashboards.

Contact the platform team for:
- Grafana access and credentials
- Help creating custom dashboards for your team's events
- Queries to filter events by your `agent_id`

