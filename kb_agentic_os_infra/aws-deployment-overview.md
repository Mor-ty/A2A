# AWS AgentCore Deployment Guide

This guide explains how to deploy your agent to the AWS AgentCore runtime using the deployment scripts provided in the `agentic_os_infra` SDK.

---

## The A2A Wrapper

To deploy the agent to AWS without modifying its core logic, all AWS-specific plumbing is isolated inside the `aws_deployment` module of the SDK.

AWS AgentCore's **A2A (Agent-to-Agent) protocol** requires the application to expose an HTTP server on port `9000` with a `/ping` health check endpoint. The `agent.py` wrapper handles this by dynamically importing your existing application, adding the required health check, and serving it via Uvicorn on the correct port.

Your `__main__.py` requires **no AWS-specific code** — it only needs a `create_app()` function that returns a Starlette application.

---

## Module File Reference

| File | Purpose |
|---|---|
| `deploy_agentcore.py` | Main automation script — downloads SDK, configures, patches yaml, launches |
| `Dockerfile` | Container definition — installs SDK zip, Python deps, sets entrypoint |
| `agent.py` | Runtime wrapper — dynamic import of `__main__.py`, `/ping` route, Uvicorn on port 9000 |
| `requirements_agentcore.txt` | Python dependencies needed inside the container (Uvicorn, AWS SDKs, etc.) |
| `runtime_url.py` | Helper to construct the agent's invocation URL from its ARN |
| `.dockerignore` | Excludes `.venv`, `.git`, etc. from the Docker build context |
| `aws_agentcore_mcp_bridge.py` | Proxies MCP tool calls to another AgentCore runtime via the A2A protocol |

---

## Container Protocol Requirements

When deploying to AgentCore runtime, the container must meet the following requirements:

**Protocol-specific ports and paths:**

| Protocol | Port | Path | Notes |
|---|---|---|---|
| **A2A** | `9000` | `/` | Used by this agent |
| **HTTP** | `8080` | `/invocations` | — |
| **MCP** | `8000` | `/mcp` | — |

**All containers must also:**
*   Bind to `0.0.0.0` (not `localhost` or `127.0.0.1`)
*   Expose `GET /ping` returning `{"status": "ok"}` — AgentCore uses this to verify container readiness
*   Be fully stateless — no local disk state that must survive restarts (use AgentCore Memory instead)

---

## Required Environment Variables

### Set in `.env` (local / deploy machine)

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENT_NAME` | ✅ | — | Name of the agent, used for AWS resource naming |
| `AGENTCORE_AGENT_ARN` | After 1st deploy | — | ARN of the deployed runtime, used by client scripts |
| `AWS_DEFAULT_REGION` | ✅ | — | AWS region for AgentCore deployment (e.g. `eu-west-1`) |
| `AWS_REGION` | ✅ | — | AWS region for Bedrock model calls (e.g. `us-east-1`) |
| `MCP_NAME` | ✅ | — | ARN or URL of the connected MCP server |
| `LOCAL_SDK_PATH` | ❌ | — | Path to a local SDK zip — skips the S3 download |
| `AGENT_ENTRYPOINT` | ❌ | `__main__.py` | Entrypoint filename, if different from `__main__.py` |

### Injected into the container by `agentcore launch`

| Variable | Value | Description |
|---|---|---|
| `AWS_DEPLOY` | `true` | Activates AgentCore Memory-backed config and context stores |
| `AGENT_ENTRYPOINT` | `__main__.py` | Bare filename — resolved to `/app/__main__.py` inside the container |
| `RABBITMQ_ENABLED` | `false` | Disables the telemetry message broker |
| `AWS_DEFAULT_REGION` | `eu-west-1` | Container region |
| `AWS_REGION` | `eu-west-1` | Container region |

---

## The Deployment Process

When you run the deployment module, the following steps occur automatically:

**Step 1 — SDK Handling**

Checks for a local SDK file via `LOCAL_SDK_PATH`. If not found, downloads `agentic_os_infra.zip` from S3 (`s3://agent-zip-files/agent_infra/`) into the project root, making it available to the Docker build context.

**Step 2 — `agentcore configure`**

Runs `agentcore configure` to write `.bedrock_agentcore.yaml` with deployment metadata (ECR repo, execution role, region, protocol).

> **Important — yaml entrypoint patch**: `agentcore configure` writes the absolute local Mac path into the yaml (e.g. `/Users/you/.../agent_template/__main__.py`). When `agentcore launch` later reads this it injects that path as `AGENT_ENTRYPOINT` into the container, causing a `FileNotFoundError`. The deploy script immediately patches the yaml after configure to reset the value to the bare filename:
> ```python
> _cfg["agents"][AGENT_NAME]["entrypoint"] = ENTRYPOINT_FILE  # "__main__.py"
> ```

**Step 3 — Copy Custom Dockerfile**

`agentcore configure` regenerates the Dockerfile from its own Jinja template. The deploy script overwrites it with the project's custom Dockerfile, which knows how to install `agentic_os_infra.zip`.

**Step 4 — `agentcore launch`**

Runs `agentcore launch` with all required environment variables injected into the container. This triggers AWS CodeBuild to build the Docker image, push it to ECR, and deploy new container instances to the AgentCore runtime.

**Step 5 — Cleanup**

Removes temporary files from the project root (`agentic_os_infra.zip`, `requirements_agentcore.txt`, `aws_deployment_tmp/`).

---

## How to Deploy

**Prerequisites:** SDK installed in `.venv`, `.env` configured, AWS credentials active.

1.  **Ensure the SDK is installed** in your virtual environment.

2.  **Configure your `.env`** file in the project root:
    ```env
    AGENT_NAME=my_agent
    AWS_DEFAULT_REGION=eu-west-1
    AWS_REGION=us-east-1
    MCP_NAME=arn:aws:bedrock-agentcore:...
    ```

3.  **Verify your entrypoint** — `__main__.py` must have a `create_app()` function that returns a Starlette app.

4.  **Run the deploy script:**
    ```bash
    python -m agentic_os_infra.aws_deployment.deploy_agentcore
    ```

---

## CloudWatch GenAI Observability

Agent invocations, token counts, latency, and full LangChain/Bedrock call traces are visible in the **CloudWatch → GenAI Observability → Model Invocations** dashboard.

### How it works

The AgentCore runtime starts an **OpenTelemetry sidecar** alongside the container when `observability: enabled: true` is set in `.bedrock_agentcore.yaml`. The sidecar collects spans from the `opentelemetry-instrument` process and ships them to AWS X-Ray / CloudWatch Transaction Search.

The full pipeline:

```
opentelemetry-instrument python -m agent   (container ENTRYPOINT)
        │
        ▼  AwsOpenTelemetryConfigurator  (aws_configurator)
        │  BotocoreInstrumentor  ← auto-applied by opentelemetry-instrument
        │  LangchainInstrumentor ← auto-applied (opentelemetry-instrumentation-langchain)
        │
        ▼  OTLP HTTP spans → AgentCore runtime OTEL sidecar (port 4318)
        │
        ▼  AWS X-Ray  →  CloudWatch Transaction Search  →  aws/spans log group
        │
        ▼  CloudWatch GenAI Observability dashboard
```

### Account-level prerequisites (one-time setup)

These must be configured once per AWS account / region before any spans appear on the dashboard:

1. **Enable CloudWatch Transaction Search**

   ```bash
   # Create the resource policy that allows X-Ray to write to CloudWatch Logs
   aws logs put-resource-policy \
     --policy-name TransactionSearchAccessPolicy \
     --policy-document '{
       "Version":"2012-10-17",
       "Statement":[{
         "Sid":"AWSLogDeliveryWrite",
         "Effect":"Allow",
         "Principal":{"Service":"xray.amazonaws.com"},
         "Action":["logs:CreateLogGroup","logs:CreateLogDelivery",
                   "logs:PutLogEvents","logs:DescribeLogGroups"],
         "Resource":"*"
       }]
     }'

   # Point X-Ray segment destination to CloudWatch Logs
   aws xray update-trace-segment-destination --destination CloudWatchLogs

   # Bump the indexing rule from default 1 % to 100 %
   aws xray update-indexing-rule \
     --name "Default" \
     --rule '{"Probabilistic":{"DesiredSamplingPercentage":100}}'
   ```

2. **`observability: enabled: true`** in `.bedrock_agentcore.yaml` (already set by `agentcore configure`).

### Changes made to the SDK (`aws_deployment/`)

| File | What changed |
|---|---|
| `Dockerfile` | `ENTRYPOINT` changed to `["opentelemetry-instrument", "python", "-m", ...]` — this starts the OTEL sidecar |
| `requirements_agentcore.txt` | Added `aws-opentelemetry-distro~=0.12.1` and `opentelemetry-instrumentation-langchain` |
| `agent.py` | Removed manual `AwsOpenTelemetryConfigurator().configure()` call (double-init drops all spans); now logs a delegation message only |
| `deploy_agentcore.py` | Three OTEL env vars added to `env_vars` list (see below) |

### Env vars injected into the container

In addition to the standard env vars, these three are now passed by `deploy_agentcore.py`:

| Variable | Value | Why |
|---|---|---|
| `OTEL_PYTHON_CONFIGURATOR` | `aws_configurator` | Selects the AWS ADOT configurator (not the default OpenTelemetry one); required for `gen_ai.*` semantic conventions |
| `AGENT_OBSERVABILITY_ENABLED` | `true` | Activates the `gen_ai_agent` export path inside `AwsOpenTelemetryConfigurator`; without it `_get_exporter_names()` returns `[]` and all spans are silently discarded |
| `OTEL_TRACES_EXPORTER` | `otlp_proto_http` | Forces HTTP OTLP (port 4318) — the runtime sidecar only listens on HTTP; `otlp` silently maps to gRPC (port 4317) which is not available |

### What appears in the dashboard

Once spans are flowing, the following data is available per model call:

| Span name | Key `gen_ai.*` attributes |
|---|---|
| `chat <model-id>` | `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons` |
| `ChatBedrock.chat` | `gen_ai.prompt.*` roles, `gen_ai.completion.*`, tool calls, token counts |

Memory operation spans (`Bedrock AgentCore.CreateEvent`, `ListEvents`, `DeleteEvent`) and A2A framework spans are also emitted.

### Verifying the pipeline after deployment

```bash
# 1. Check no exporter errors in container logs
AWS_DEFAULT_REGION=eu-west-1 aws logs tail \
  /aws/bedrock-agentcore/runtimes/<agent-id>-DEFAULT \
  --since 10m 2>&1 | grep -E "4317|4318|UNAVAILABLE|refused"
# Expected: no output (silence = success)

# 2. Check the OTEL sidecar log stream exists and is active
AWS_DEFAULT_REGION=eu-west-1 aws logs tail \
  /aws/bedrock-agentcore/runtimes/<agent-id>-DEFAULT \
  --log-stream-names otel-rt-logs --since 5m 2>&1 | head -5
# Expected: JSON log lines with "aws.service.type":"gen_ai_agent"

# 3. Check aws/spans for gen_ai.* span attributes from your agent
AWS_DEFAULT_REGION=eu-west-1 aws logs tail aws/spans --since 10m 2>&1 \
  | grep <agent-name> | grep gen_ai | head -5
# Expected: spans with gen_ai.request.model, gen_ai.usage.* etc.
```

**Dashboard URL:**
```
https://console.aws.amazon.com/cloudwatch/home?region=<region>#gen-ai-observability/agent-core
```

> **Note:** Data can take up to 10 minutes to appear after the first invocation following a new deployment.

### Common failure modes

| Symptom | Root cause | Fix |
|---|---|---|
| `localhost:4317 UNAVAILABLE` in logs | `OTEL_TRACES_EXPORTER=otlp` maps to gRPC; sidecar only listens on HTTP | Set `OTEL_TRACES_EXPORTER=otlp_proto_http` |
| `localhost:4318 Connection refused` | Container started with plain `python` entrypoint — runtime never started the sidecar | Use `opentelemetry-instrument python ...` as `ENTRYPOINT` |
| Spans exported but dashboard empty | `AGENT_OBSERVABILITY_ENABLED` not set — `AwsOpenTelemetryConfigurator` runs without the `gen_ai_agent` export path | Add `AGENT_OBSERVABILITY_ENABLED=true` to container env vars |
| Spans exported but no `gen_ai.*` attrs | `OTEL_PYTHON_CONFIGURATOR` not set — default distro used instead of AWS ADOT | Add `OTEL_PYTHON_CONFIGURATOR=aws_configurator` |
| `aws/spans` log group empty | Transaction Search not enabled or indexing rule at 1% | Run the one-time account setup commands above |
| Dashboard shows data from **other** agents only | Container still running old image (cached session routing) | Use a fresh `uuid.uuid4()` session ID to force a new container |

