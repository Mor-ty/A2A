"""Shared pytest fixtures for the agent_template test suite."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from a2a.types import TaskState, TaskStatusUpdateEvent, TaskArtifactUpdateEvent

# Avoid importing layer classes at module import time because some upstream
# modules perform telemetry/network initialization on import which breaks
# tests in isolated environments. Import the classes lazily inside fixtures.


# helpers

def make_input_data(user_query="hello", extra_inputs: dict | None = None) -> dict:
    """Build the minimal input_data dict that AgentLogicLayer.run() expects."""
    inputs = {"user_query": user_query}
    if extra_inputs:
        inputs.update(extra_inputs)
    return {"entityConfig": {"inputs": inputs}}


class FakeTool:
    """Minimal tool descriptor returned by mcp_wrapper.list_tools()."""
    def __init__(self, name: str):
        self.name = name


class FakeLLMResponse:
    """Simulates an LLM response object with .content and .tool_calls."""
    def __init__(self, content: str = "llm answer", tool_calls: list | None = None):
        self.content = content
        self.tool_calls = tool_calls or []



# fixtures

@pytest.fixture
def monitoring_metadata():
    return {
        "task_id": "test-task-id",
        "context_id": "test-context-id",
        "element_id": "test-element-id",
        "agent_id": "test-agent-id",
        "session_id": "test-session-id",
        "experience_id": "test-exp-id",
        "execution_id": "test-exec-id",
    }


@pytest.fixture
def mock_llm_adapter():
    """MagicMock wired to behave like an LLM adapter."""
    adapter = MagicMock()
    adapter.system_prompt = "You are a helpful agent."

    adapter.client.bind_tools.return_value = adapter.client

    adapter.llm_chat = AsyncMock(return_value=FakeLLMResponse("llm answer"))
    adapter.format_tools.side_effect = lambda t: t          # identity
    adapter.create_tool_message.return_value = {"role": "tool", "content": "tool result"}
    return adapter


@pytest.fixture
def mock_mcp_wrapper():
    """MagicMock wired to behave like a CustomMCPWrapper."""
    wrapper = MagicMock()
    wrapper.list_tools = AsyncMock(return_value=[FakeTool("echo_tool")])

    tool_result = MagicMock()
    tool_result.data = "tool output"
    wrapper.call_tool = AsyncMock(return_value=tool_result)
    return wrapper


@pytest.fixture
def agent_logic(mock_mcp_wrapper, mock_llm_adapter, monitoring_metadata):
    # Import lazily to avoid telemetry/network side effects at import time
    from layers.agent_logic import AgentLogicLayer
    return AgentLogicLayer(
        mcp_wrapper=mock_mcp_wrapper,
        llm_adapter=mock_llm_adapter,
        monitoring_metadata=monitoring_metadata,
    )


@pytest.fixture
def agent_logic_no_mcp(mock_llm_adapter, monitoring_metadata):
    from layers.agent_logic import AgentLogicLayer
    return AgentLogicLayer(
        mcp_wrapper=None,
        llm_adapter=mock_llm_adapter,
        monitoring_metadata=monitoring_metadata,
    )


@pytest.fixture
def compliance_layer(mock_mcp_wrapper, monitoring_metadata):
    from layers.compliance import ComplianceLayer
    return ComplianceLayer(mock_mcp_wrapper, monitoring_metadata)


@pytest.fixture
def evaluation_layer(mock_mcp_wrapper, monitoring_metadata):
    from layers.evaluation import EvaluationLayer
    return EvaluationLayer(mock_mcp_wrapper, monitoring_metadata)


@pytest.fixture
def guardrails_layer(mock_mcp_wrapper, monitoring_metadata):
    from layers.guardrails import GuardrailsLayer
    return GuardrailsLayer(mock_mcp_wrapper, monitoring_metadata)


@pytest.fixture
def configuration_layer(monitoring_metadata):
    from agent_card import extended_agent_card
    from layers.configuration import ConfigurationLayer
    blueprint = MagicMock()
    return ConfigurationLayer(blueprint, extended_agent_card, monitoring_metadata)
