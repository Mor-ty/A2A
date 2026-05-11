"""Tests for the Temperature Agent — agent_logic.py

Covers:
  - Tool implementations (_get_region_temperature, _convert_temperature)
  - Tool dispatch (_execute_tool)
  - Full run() with and without tool calls
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from a2a.types import TaskState, TaskStatusUpdateEvent, TaskArtifactUpdateEvent

from tests.conftest import FakeLLMResponse, make_input_data
from layers.agent_logic import (
    AgentLogicLayer,
    REGION_TEMPERATURE_METADATA,
    TEMPERATURE_TOOLS,
    _ToolResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def collect(gen) -> list:
    events = []
    async for event in gen:
        events.append(event)
    return events


def status_events(events):
    return [e for e in events if isinstance(e, TaskStatusUpdateEvent)]


def artifact_events(events):
    return [e for e in events if isinstance(e, TaskArtifactUpdateEvent)]


def get_artifact_text(events) -> str:
    arts = artifact_events(events)
    if not arts:
        return ""
    part = arts[-1].artifact.parts[0].root
    return getattr(part, "text", str(part))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def monitoring_metadata():
    return {
        "task_id": "t1", "context_id": "c1", "element_id": "e1",
        "agent_id": "a1", "session_id": "s1",
        "experience_id": "exp1", "execution_id": "exec1",
    }


@pytest.fixture
def mock_llm_adapter():
    adapter = MagicMock()
    adapter.system_prompt = (
        "You are a Temperature Agent with access to two tools: "
        "get_region_temperature and convert_temperature."
    )
    adapter.client.bind_tools.return_value = adapter.client
    adapter.llm_chat = AsyncMock(return_value=FakeLLMResponse("London is 12°C."))
    adapter.format_tools.side_effect = lambda t: t
    adapter.create_tool_message.return_value = {"role": "tool", "content": "tool result"}
    return adapter


@pytest.fixture
def agent(mock_llm_adapter, monitoring_metadata):
    return AgentLogicLayer(
        mcp_wrapper=None,
        llm_adapter=mock_llm_adapter,
        monitoring_metadata=monitoring_metadata,
    )


# ---------------------------------------------------------------------------
# Unit tests — _get_region_temperature
# ---------------------------------------------------------------------------

class TestGetRegionTemperature:
    def test_known_region_returns_temperature(self, agent):
        result = agent._get_region_temperature("London")
        assert "12.0°C" in result
        assert "London" in result

    def test_region_lookup_is_case_insensitive(self, agent):
        assert agent._get_region_temperature("LONDON") == agent._get_region_temperature("london")

    def test_unknown_region_returns_helpful_message(self, agent):
        result = agent._get_region_temperature("Atlantis")
        assert "Atlantis" in result
        assert "Available regions" in result

    def test_all_metadata_regions_resolve(self, agent):
        for region in REGION_TEMPERATURE_METADATA:
            result = agent._get_region_temperature(region)
            assert "°C" in result, f"Expected °C in result for region '{region}'"

    def test_region_with_extra_whitespace(self, agent):
        result = agent._get_region_temperature("  london  ")
        assert "12.0°C" in result


# ---------------------------------------------------------------------------
# Unit tests — _convert_temperature
# ---------------------------------------------------------------------------

class TestConvertTemperature:
    def test_freezing_point(self, agent):
        result = agent._convert_temperature(0)
        assert "32.00°F" in result
        assert "273.15 K" in result

    def test_boiling_point(self, agent):
        result = agent._convert_temperature(100)
        assert "212.00°F" in result
        assert "373.15 K" in result

    def test_body_temperature(self, agent):
        result = agent._convert_temperature(37)
        assert "98.60°F" in result
        assert "310.15 K" in result

    def test_negative_celsius(self, agent):
        result = agent._convert_temperature(-40)
        assert "-40.00°F" in result   # -40 is the cross-over point
        assert "233.15 K" in result

    def test_output_contains_all_three_units(self, agent):
        result = agent._convert_temperature(20)
        assert "°C" in result
        assert "°F" in result
        assert "K" in result


# ---------------------------------------------------------------------------
# Unit tests — _execute_tool
# ---------------------------------------------------------------------------

class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_dispatches_get_region_temperature(self, agent):
        result = await agent._execute_tool("get_region_temperature", {"region": "Paris"})
        assert isinstance(result, _ToolResult)
        assert "14.0°C" in result.data

    @pytest.mark.asyncio
    async def test_dispatches_convert_temperature(self, agent):
        result = await agent._execute_tool("convert_temperature", {"celsius": 0})
        assert isinstance(result, _ToolResult)
        assert "32.00°F" in result.data

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_message(self, agent):
        result = await agent._execute_tool("fly_to_moon", {})
        assert "Unknown tool" in result.data


# ---------------------------------------------------------------------------
# Integration tests — run()
# ---------------------------------------------------------------------------

class TestRunNoToolCalls:
    @pytest.mark.asyncio
    async def test_first_event_is_working_status(self, agent):
        events = await collect(agent.run(make_input_data("What is the temperature in London?")))
        assert events, "run() yielded no events"
        assert isinstance(events[0], TaskStatusUpdateEvent)
        assert events[0].status.state == TaskState.working

    @pytest.mark.asyncio
    async def test_emits_artifact_at_end(self, agent):
        events = await collect(agent.run(make_input_data("temperature in london")))
        arts = artifact_events(events)
        assert arts, "No artifact events emitted"

    @pytest.mark.asyncio
    async def test_system_prompt_seeded_on_first_run(self, agent):
        await collect(agent.run(make_input_data("hello")))
        assert agent.messages[0]["role"] == "system"
        assert "Temperature Agent" in agent.messages[0]["content"]

    @pytest.mark.asyncio
    async def test_system_prompt_not_duplicated_on_second_run(self, agent):
        await collect(agent.run(make_input_data("first")))
        await collect(agent.run(make_input_data("second")))
        system_msgs = [m for m in agent.messages if m.get("role") == "system"]
        assert len(system_msgs) == 1

    @pytest.mark.asyncio
    async def test_llm_called_once_when_no_tool_calls(self, agent, mock_llm_adapter):
        await collect(agent.run(make_input_data("hello")))
        assert mock_llm_adapter.llm_chat.call_count == 1

    @pytest.mark.asyncio
    async def test_tools_bound_to_llm_client(self, agent, mock_llm_adapter):
        await collect(agent.run(make_input_data("temperature in tokyo")))
        mock_llm_adapter.client.bind_tools.assert_called_once_with(TEMPERATURE_TOOLS)


class TestRunWithToolCalls:
    """Run() when the LLM returns tool_calls on the first response."""

    @pytest.fixture
    def agent_with_tool_call(self, mock_llm_adapter, monitoring_metadata):
        """LLM first returns a tool call, then returns a final answer."""
        tool_call = {"name": "get_region_temperature", "args": {"region": "Dubai"}, "id": "tc_001"}

        first_response = FakeLLMResponse(
            content="",
            tool_calls=[tool_call],
        )
        second_response = FakeLLMResponse(content="Dubai is 38°C (100.40°F, 311.15 K).")

        mock_llm_adapter.llm_chat = AsyncMock(side_effect=[first_response, second_response])
        mock_llm_adapter.create_tool_message.side_effect = (
            lambda call, result: {"role": "tool", "content": result.data}
        )

        return AgentLogicLayer(
            mcp_wrapper=None,
            llm_adapter=mock_llm_adapter,
            monitoring_metadata=monitoring_metadata,
        )

    @pytest.mark.asyncio
    async def test_llm_called_twice_when_tool_call_present(self, agent_with_tool_call, mock_llm_adapter):
        await collect(agent_with_tool_call.run(make_input_data("temperature in Dubai")))
        assert mock_llm_adapter.llm_chat.call_count == 2

    @pytest.mark.asyncio
    async def test_tool_result_appended_to_messages(self, agent_with_tool_call):
        await collect(agent_with_tool_call.run(make_input_data("temperature in Dubai")))
        tool_msgs = [m for m in agent_with_tool_call.messages if isinstance(m, dict) and m.get("role") == "tool"]
        assert tool_msgs, "No tool message found in conversation history"
        assert "38.0°C" in tool_msgs[0]["content"]

    @pytest.mark.asyncio
    async def test_artifact_contains_final_llm_response(self, agent_with_tool_call):
        events = await collect(agent_with_tool_call.run(make_input_data("temperature in Dubai")))
        arts = artifact_events(events)
        assert arts, "No artifact emitted"


# ---------------------------------------------------------------------------
# Tool schema integrity tests
# ---------------------------------------------------------------------------

class TestToolSchemas:
    def test_two_tools_defined(self):
        assert len(TEMPERATURE_TOOLS) == 2

    def test_get_region_temperature_schema(self):
        schema = next(t for t in TEMPERATURE_TOOLS if t["function"]["name"] == "get_region_temperature")
        params = schema["function"]["parameters"]
        assert "region" in params["properties"]
        assert "region" in params["required"]

    def test_convert_temperature_schema(self):
        schema = next(t for t in TEMPERATURE_TOOLS if t["function"]["name"] == "convert_temperature")
        params = schema["function"]["parameters"]
        assert "celsius" in params["properties"]
        assert "celsius" in params["required"]

    def test_all_tools_have_type_function(self):
        for tool in TEMPERATURE_TOOLS:
            assert tool.get("type") == "function"
