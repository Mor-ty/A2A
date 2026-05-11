# AWS AgentCore Deployment Guide

This guide covers everything you need to deploy **your own agent** to Amazon Bedrock AgentCore Runtime using the `agentic_os_infra` SDK.

It is split into three independent topics you can read in any order:

| # | Topic | What it answers |
|---|---|---|
| [1](#1-environment-variables) | **Environment Variables** | What to put in `.env` and what gets injected into the container |
| [2](#2-what-to-implement-in-your-agent) | **What to Implement in Your Agent** | The files you must write outside the SDK |
| [3](#3-client-configuration--local-vs-aws) | **Client Configuration** | `client.py` (local) vs `client_aws.py` (AWS) |
| [4](#4-deploying) | **Deploying** | How to run the deploy script |
| [5](#5-cloudwatch--observability) | **Observability** | CloudWatch logs and GenAI tracing |

---

## 1. Environment Variables

### 1.1 — Set in your local `.env` before deploying

These are read by the **deploy script on your machine**. Create a `.env` file in your project root:

```env
AGENT_NAME=my_agent
AWS_DEFAULT_REGION=eu-west-1
AWS_REGION=us-east-1
MCP_NAME=arn:aws:bedrock-agentcore:eu-west-1:<account-id>:mcp-server/<name>
AGENTCORE_AGENT_ARN=                  # leave blank until after first deploy
```

| Variable | Required | Description |
|---|---|---|
| `AGENT_NAME` | ✅ | Name for the agent — used for ECR repo, runtime, and log group naming |
| `AWS_DEFAULT_REGION` | ✅ | Region where AgentCore deploys the container (e.g. `eu-west-1`) |
| `AWS_REGION` | ✅ | Region for Bedrock model calls — can differ from deploy region (e.g. `us-east-1`) |
| `MCP_NAME` | ✅ | ARN or URL of the MCP server this agent connects to |
| `AGENTCORE_AGENT_ARN` | After 1st deploy | The runtime ARN printed after a successful deploy — used by `client_aws.py` |
| `LOCAL_SDK_PATH` | ❌ | Absolute path to a local `agentic_os_infra.zip` — skips the S3 download, useful when testing SDK changes |
| `AGENT_ENTRYPOINT` | ❌ | Override the entrypoint filename if it is not `__main__.py` |

> **After your first deploy** the deploy script prints the runtime ARN.
> Copy it into `.env` as `AGENTCORE_AGENT_ARN` so `client_aws.py` can invoke the deployed agent.

---

### 1.2 — Injected automatically into the container by `agentcore launch`

You do **not** need to set these yourself — the deploy script passes them to the container on every deploy.

| Variable | Value | What it does |
|---|---|---|
| `AWS_DEPLOY` | `true` | Switches the executor from `SQLiteConfigStore` to `AgentCoreConfigStore` (AgentCore Memory-backed). **This is the key flag that activates production storage.** |
| `AGENT_ENTRYPOINT` | `__main__.py` | Bare filename resolved to `/app/__main__.py` inside the container |
| `RABBITMQ_ENABLED` | `false` | Disables the telemetry message broker |
| `AWS_DEFAULT_REGION` | *(from `.env`)* | Region forwarded into the container |
| `AWS_REGION` | *(from `.env`)* | Region forwarded into the container |
| `OTEL_PYTHON_CONFIGURATOR` | `aws_configurator` | Selects the AWS ADOT OpenTelemetry configurator |
| `AGENT_OBSERVABILITY_ENABLED` | `true` | Enables the `gen_ai_agent` span export path |
| `OTEL_TRACES_EXPORTER` | `otlp_proto_http` | Routes traces to the runtime sidecar over HTTP (port 4318) |

---

## 2. What to Implement in Your Agent

The SDK handles all AWS plumbing. You only need to write **three things** in your project:

```
your_agent/
├── __main__.py        ← required: must expose create_app()
├── agent_card.py      ← required: must define public_agent_card + extended_agent_card
├── layers/
│   ├── configuration.py   ← your agent logic
│   ├── guardrails.py
│   ├── agent_logic.py
│   ├── evaluation.py
│   └── compliance.py
└── input.json         ← payload sent by the client
```

---

### 2.1 — `__main__.py` — the entrypoint

The **only requirement** is a `create_app()` function that returns a Starlette application.
The SDK wrapper (`agent.py`) dynamically imports this function — no AWS-specific code belongs here.

```python
# __main__.py — minimal required shape

def create_app():
    shared_store = SQLiteConfigStore("config_store.db")         # SDK overrides this when AWS_DEPLOY=true
    context_data_store = SQLiteContextDataStore("config_store.db")

    request_handler = DefaultRequestHandler(
        agent_executor=MyAgentExecutor(
            configuration_layer=ConfigurationLayer,
            guardrails_layer=GuardrailsLayer,
            logic_layer=AgentLogicLayer,
            evaluation_layer=EvaluationLayer,
            compliance_layer=ComplianceLayer,
            extended_agent_card=extended_agent_card,
            config_store=shared_store,
            context_data_store=context_data_store,
        ),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(...).build()
    return app   # ← this is all the SDK needs
```

> **`SQLiteConfigStore` is safe to pass here.**
> When `AWS_DEPLOY=true` the executor automatically replaces it with `AgentCoreConfigStore` (AgentCore Memory).
> Your `__main__.py` never needs to know about AWS.

---

### 2.2 — `agent_card.py` — agent identity

Define two objects that both `__main__.py` and the client scripts import:

| Object | Type | Used by |
|---|---|---|
| `public_agent_card` | `AgentCard` | `client.py`, `client_aws.py` — the card that describes your agent to callers |
| `extended_agent_card` | `ExtendedAgentCard` | `__main__.py` — adds SDK-specific fields (skills, enrichments, system prompt, etc.) |

Minimum fields to fill in (marked `#TODO` in the template):

```python
from agentic_os_infra.aws_deployment.runtime_url import agent_url, server
# agent_url — auto-resolved base URL: localhost locally, AgentCore runtime URL in production
# server    — bare hostname, useful for icon/asset URLs (e.g. f"https://{server}/...")

public_agent_card = AgentCard(
    name='Your Agent Name',          # human-readable name
    description='What it does',
    url=agent_url,                   # imported from agentic_os_infra.aws_deployment.runtime_url
    ...
)

extended_agent_card = extended_agent_card.model_copy(update={
    'id': '<your-uuid>',             # stable UUID for this agent
    'system_prompt': "You are ...",  # the agent's system prompt
    ...
})
```

> `agent_url` is auto-resolved from `runtime_url.py` — it points to `localhost` locally and to the AgentCore runtime URL in production.

---

### 2.3 — `layers/` — agent logic

Implement the five layers. Each layer is a class with an async `process()` method. The executor calls them in order:

| Layer | File | What to implement |
|---|---|---|
| **Configuration** | `layers/configuration.py` | Parse the incoming request, build `mcp_wrapper` + `sub_agent_wrapper`, persist to store |
| **Guardrails** | `layers/guardrails.py` | Pre-flight safety checks before the agent runs |
| **Agent Logic** | `layers/agent_logic.py` | Core LLM reasoning and MCP tool calls |
| **Evaluation** | `layers/evaluation.py` | Post-run quality checks |
| **Compliance** | `layers/compliance.py` | Final policy / compliance filter |

The SDK executor wires them together — you only write the business logic inside each layer.

---

### 2.4 — The two-call protocol

Every session requires **exactly two sequential calls** from the client:

```
Call 1 — description: "Configuration"
  └─ ConfigurationLayer runs, builds and persists the agent config (mcp_wrapper, etc.)
  └─ Returns: "Configuration step completed successfully"

Call 2 — description: "message"
  └─ Executor loads config from store, runs all layers
  └─ Returns: the agent's response
```

Both calls must use the **same `context_id`** so the executor can match the stored config to the message call.

---

## 3. Client Configuration — Local vs AWS

Use **`client.py`** for local development and **`client_aws.py`** when invoking the agent deployed on AWS.

### At a glance

| | `client.py` | `client_aws.py` |
|---|---|---|
| **Target** | Local Uvicorn server | AWS AgentCore Runtime |
| **URL** | `agent_url` from `agent_card.py` (e.g. `http://localhost:9996`) | Built from `AGENTCORE_AGENT_ARN` in `.env` |
| **Authentication** | None | AWS SigV4 — signs every request using your local AWS credentials |
| **Session header** | Not needed | `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` — routes both calls to the same container |
| **Extra dependencies** | `httpx` | `httpx`, `boto3`, `botocore` |
| **When to use** | Day-to-day development and testing | Calling a deployed agent on AWS |

---

### 3.1 — `client.py` (local)

Connects directly to the local server. No auth, no special headers.

```python
# client.py — key difference from client_aws.py
async def main():
    async with httpx.AsyncClient(timeout=timeout) as httpx_client:
        client = A2AClient(httpx_client=httpx_client, agent_card=public_agent_card)
        #                                                          ^^^^^^^^^^^^^^^^
        #                                          points to localhost via agent_card.py's agent_url
        await interactive_loop(client=client)
```

Start your local server first:
```bash
python __main__.py       # starts on port 9996 by default
python client.py         # send a request
```

---

### 3.2 — `client_aws.py` (AWS)

Targets the deployed runtime. Three things differ from `client.py`:

**① The URL is built from the runtime ARN:**
```python
# Requires AGENTCORE_AGENT_ARN in .env
RUNTIME_URL = build_runtime_url(os.getenv("AGENTCORE_AGENT_ARN"))
# → https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<encoded-arn>/invocations/

deployed_agent_card = public_agent_card.model_copy(update={"url": RUNTIME_URL})
```

**② Every request is signed with AWS SigV4:**
```python
async with httpx.AsyncClient(
    auth=AwsSigV4Auth(region=REGION),   # signs using your local AWS credential chain
    ...
) as httpx_client:
    client = A2AClient(httpx_client=httpx_client, agent_card=deployed_agent_card)
```

**③ A fixed session ID is sent as a header:**
```python
# Both the config call and the message call MUST use the same session_id.
# AgentCore uses this to route both requests to the same container instance
# so the stored config from call 1 is still in memory for call 2.
session_id = "12345678-1234-5678-1234-567812345678"   # any stable UUID
extra_headers = {
    "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
}
```

> **Why the session header matters:** AgentCore may run multiple container instances. Without a fixed session ID, call 1 (Config) and call 2 (message) could hit different containers — and the second one would have no stored config.

---

### 3.3 — Running against AWS

```bash
# 1. Make sure AGENTCORE_AGENT_ARN is set in .env
# 2. Ensure your AWS credentials are active (aws sso login, or env vars)

# Send the configuration call first (input.json: description = "Configuration")
python client_aws.py
# Expected output: "Configuration step completed successfully"

# Then send the message call (input.json: description = "message")
python client_aws.py
# Expected output: the agent's response
```

---

## 4. Deploying

### Prerequisites
- `agentic_os_infra` SDK installed in `.venv`
- `.env` configured with all ✅ required variables (see [Section 1.1](#11--set-in-your-local-env-before-deploying))
- AWS credentials active (`aws sso login` or environment variables)

### Run the deploy script

```bash
python -m agentic_os_infra.aws_deployment.deploy_agentcore
```

The script runs these steps automatically:

| Step | What happens |
|---|---|
| **1 — SDK** | Downloads `agentic_os_infra.zip` from S3 (or uses `LOCAL_SDK_PATH` if set) into the project root so Docker can COPY it |
| **2 — Configure** | Runs `agentcore configure` to write `.bedrock_agentcore.yaml`; then patches the entrypoint path from an absolute Mac path to the bare filename `__main__.py` |
| **3 — Dockerfile** | Overwrites the auto-generated Dockerfile with the custom one that installs `agentic_os_infra.zip` |
| **4 — Launch** | Runs `agentcore launch` — triggers CodeBuild → ECR push → AgentCore runtime update |
| **5 — Cleanup** | Removes temporary files (`agentic_os_infra.zip`, `requirements_agentcore.txt`, `aws_deployment_tmp/`) |

After a successful deploy the script prints the **runtime ARN**. Copy it to `.env` as `AGENTCORE_AGENT_ARN`.

### What runs inside the container

The Docker `ENTRYPOINT` is not your `__main__.py` — it is the SDK wrapper:

```dockerfile
ENTRYPOINT ["opentelemetry-instrument", "python", "-m", "agentic_os_infra.aws_deployment.agent"]
```

`agent.py` dynamically imports your `create_app()`, adds the `/ping` health-check route required by AgentCore, and starts Uvicorn on port `9000`.

### Container requirements (enforced by AgentCore)

| Requirement | Value |
|---|---|
| Protocol | A2A |
| Port | `9000` |
| Bind address | `0.0.0.0` |
| Health check | `GET /ping` → `{"status": "ok"}` |
| State | Fully stateless — config is persisted in AgentCore Memory, not on disk |

### Updating the SDK

If you modify the `agentic_os_infra` package locally, re-zip and upload before deploying:

```bash
cd .venv/lib/python3.13/site-packages
zip -r /tmp/agentic_os_infra_new.zip agentic_os_infra/
aws s3 cp /tmp/agentic_os_infra_new.zip s3://agent-zip-files/agent_infra/agentic_os_infra.zip \
  --region eu-west-1
```

Then run the deploy script — it pulls the new zip from S3 and bakes it into the image.

---

## 5. CloudWatch & Observability

### Log group

```
/aws/bedrock-agentcore/runtimes/<agent-name>-<id>-DEFAULT
```

Tail live logs:
```bash
export AWS_DEFAULT_REGION=eu-west-1
aws logs tail /aws/bedrock-agentcore/runtimes/<agent-name>-<id>-DEFAULT --follow
```

### Key log messages to look for

| Message | Meaning |
|---|---|
| `[AgentExecutor] AWS_DEPLOY=true → using AgentCore Memory-backed stores` | Container started with production stores |
| `[AgentCoreConfigStore] ✓ Stored config for context_id=...` | Config call persisted successfully |
| `[AgentCoreConfigStore] ✓ Retrieved config for context_id=...` | Message call loaded config from memory |
| `Loaded keys from storage: ['input_data', 'mcp_wrapper', ...]` | All wrappers reconstructed — agent is ready |
| *(only `Loaded keys from storage`, none of the above)* | Container is using SQLite fallback — `AWS_DEPLOY=true` was not injected |

### GenAI Observability (CloudWatch dashboard)

Agent invocations, token counts, latency, and LangChain/Bedrock traces appear in
**CloudWatch → GenAI Observability → Model Invocations**.

This requires a one-time account setup:

```bash
# 1. Allow X-Ray to write to CloudWatch Logs
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

# 2. Point X-Ray segment destination to CloudWatch Logs
aws xray update-trace-segment-destination --destination CloudWatchLogs

# 3. Raise sampling to 100%
aws xray update-indexing-rule --name "Default" \
  --rule '{"Probabilistic":{"DesiredSamplingPercentage":100}}'
```

Dashboard URL:
```
https://console.aws.amazon.com/cloudwatch/home?region=<region>#gen-ai-observability/agent-core
```

> Data can take up to 10 minutes to appear after the first invocation following a new deployment.

### Common failure modes

| Symptom | Root cause | Fix |
|---|---|---|
| `localhost:4317 UNAVAILABLE` in logs | `OTEL_TRACES_EXPORTER=otlp` maps to gRPC; sidecar only listens on HTTP | `OTEL_TRACES_EXPORTER=otlp_proto_http` (already set by deploy script) |
| `localhost:4318 Connection refused` | Plain `python` entrypoint — runtime never started the OTEL sidecar | Use `opentelemetry-instrument python ...` as `ENTRYPOINT` |
| Spans exported but dashboard empty | `AGENT_OBSERVABILITY_ENABLED` not set | Add to container env vars (already set by deploy script) |
| `aws/spans` log group empty | Transaction Search not enabled or sampling at 1% | Run the one-time setup commands above |
| Dashboard shows data from other agents only | Old image cached — session routed to stale container | Use a fresh `uuid.uuid4()` as the session ID to force a new container |
