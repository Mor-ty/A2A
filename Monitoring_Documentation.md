# Monitoring & Telemetry Documentation

## Overview
This project implements structured monitoring by logging all key agent events to a JSON Lines file: `logs.jsonl`.  
Each event is a single JSON object per line, enabling easy parsing and analysis.

---

## Log File
- **Path:** `logs.jsonl`  
- **Format:** Each line is a JSON object representing one event.

---

## Event Types

### 1. Request Events
Logged at the start and end of each agent request.

**Fields:**
- `session_id`, `context_id`, `task_id`, `request_id`  
- `task_type`, `kind` (request or response)  
- `location`, `timestamp_sent` / `timestamp_received`  
- `user_input`, `number_of_chars`, `status`  
- `total latency` (for end events)  

**Functions:**
- `log_request_start` → writes start event  
- `log_request_end` → writes end event  

---

### 2. MCP Tool Calls
Logged for every MCP tool invocation.

**Fields:**
- `session_id`, `context_id`, `task_id`, `request_id`  
- `task_type`, `kind` (mcp)  
- `location`, `timestamp_received`  
- `mcp_tool`, `mcp_latency`, `mcp_response_preview`  

**Function:**
- `log_mcp_call`  

---

### 3. LLM Interactions
Logged for every LLM call.

**Fields:**
- `session_id`, `context_id`, `task_id`, `request_id`  
- `task_type`, `kind` (llm)  
- `location`, `timestamp_received`  
- `llm_model`, `llm_version`, `model_provider`  
- `llm_latency`, `temperature`  
- `response`, `response_char_count`, `response_word_count`  
- `prompt_tokens`, `completion_tokens`, `total_tokens`  

**Function:**
- `log_llm_interaction`  

---

## Implementation Details
- All logging functions use `write_jsonl(event)` from `agentic_qube_infra/core/obs.py` to append events to `logs.jsonl`.  
- Timestamps are in **ISO8601 format (UTC+3)**.  
- Context variables (`session_id_var`, `context_id_var`, etc.) ensure correlation across events.  

### Identifier semantics

| Identifier    | Scope / Purpose                                                                 |
|---------------|---------------------------------------------------------------------------------|
| `session_id`  | Represents the **entire workflow run** (end-to-end execution).                  |
| `context_id`  | Represents a **single agent instance** participating in the workflow.           |
| `task_id`     | Represents a **general task** such as configuration or execution.               |
| `request_id`  | Represents a **specific task instance** within the agent (e.g., one `mcp_call`). |

---

## Monitoring Implementation in Key Layers

### Agent Logic (`layers/agent_logic.py`)
Monitoring is performed by logging each LLM interaction using `log_llm_interaction`.  
After the agent logic runs and receives a response from the LLM adapter, it records details such as latency, model info, and response content to `logs.jsonl`.

### Agent Execution (`agentic_qube_infra/executor/agent_executor.py`)
All MCP tool calls and guardrail checks are monitored by invoking `log_mcp_call` with relevant metadata (tool name, latency, context/task IDs, etc.).  
This ensures every tool invocation and validation step is tracked in the log file.

### Adapter (`agentic_qube_infra/adapters/azure_openai_adapter_langchain.py`)
The adapter logs MCP tool invocations via `log_mcp_call` whenever the LLM requests a tool.  
It captures tool name, arguments, latency, and a preview of the result, writing these events to `logs.jsonl` for traceability.

---

## Usage
- **Monitoring:** Tail or parse `logs.jsonl` for real-time or batch analysis.  
- **Auditing:** Each event is atomic and traceable by IDs.  
- **Performance:** Latency fields allow for timing analysis of requests and tool/LLM calls.  

---

## Future Work
Currently, all telemetry is written to `logs.jsonl`. In the next stage, we plan to:  
- Introduce a **database backend** (e.g., PostgreSQL, MongoDB, or ClickHouse).  
- Move from file-based logging to structured **database storage** for scalability.  
- Enable advanced querying, aggregation, and dashboards (Grafana, Kibana, or custom tools).  
- Support hybrid mode: write to file for local debugging + database for production monitoring.  

---

## See also
- `agentic_qube_infra/core/request_telemetry.py`  
- `agentic_qube_infra/core/mcp_telemetry.py`  
- `agentic_qube_infra/core/llm_telemetry.py`
