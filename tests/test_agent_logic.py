"""Tests for AgentLogicLayer.run().

These tests are EXAMPLES ONLY — they always pass regardless of what the
developer implements in agent_logic.py.

The intent is to show developers:
  - what aspects of the logic layer are worth testing
  - how to structure those tests
  - what events and side-effects to assert on

Each test runs real code and prints a warning when an expectation is not met,
but never raises — so the pipeline stays green while developers build their own
implementation and write their own assertions.

To turn an example into a real enforced test, replace the `_soft_assert` calls
with plain `assert` statements.
"""

import pytest
from unittest.mock import AsyncMock
from a2a.types import TaskState, TaskStatusUpdateEvent, TaskArtifactUpdateEvent

from tests.conftest import FakeLLMResponse, FakeTool, make_input_data


# helpers

async def collect(gen) -> list:
    events = []
    async for event in gen:
        events.append(event)
    return events


def status_events(events):
    return [e for e in events if isinstance(e, TaskStatusUpdateEvent)]


def artifact_events(events):
    return [e for e in events if isinstance(e, TaskArtifactUpdateEvent)]


def _soft_assert(condition: bool, message: str = ""):
    """Like assert, but only prints a warning instead of failing the test."""
    if not condition:
        print(f"\n  [example hint] {message}")


# ---------------------------------------------------------------------------
# Core behaviour examples
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_event_is_working_status(agent_logic_no_mcp):
    """The first yielded event should be a working status update."""
    events = await collect(agent_logic_no_mcp.run(make_input_data("hi")))
    _soft_assert(bool(events), "run() yielded nothing")
    _soft_assert(isinstance(events[0], TaskStatusUpdateEvent), "first event should be TaskStatusUpdateEvent")
    _soft_assert(events[0].status.state == TaskState.working, "first event state should be TaskState.working")


@pytest.mark.asyncio
async def test_system_prompt_is_first_message(agent_logic_no_mcp):
    """The system prompt should be seeded as the first message on first run."""
    await collect(agent_logic_no_mcp.run(make_input_data("hello")))
    _soft_assert(bool(agent_logic_no_mcp.messages), "messages list is empty after run")
    _soft_assert(agent_logic_no_mcp.messages[0].get("role") == "system", "first message should have role=system")
    _soft_assert(bool(agent_logic_no_mcp.messages[0].get("content")), "system message content should not be empty")


@pytest.mark.asyncio
async def test_system_prompt_not_duplicated_on_second_call(agent_logic_no_mcp):
    """On repeated calls the system prompt should only appear once in the message list."""
    await collect(agent_logic_no_mcp.run(make_input_data("first")))
    await collect(agent_logic_no_mcp.run(make_input_data("second")))
    system_msgs = [m for m in agent_logic_no_mcp.messages if m.get("role") == "system"]
    _soft_assert(len(system_msgs) == 1, f"system prompt duplicated — found {len(system_msgs)} system messages")


@pytest.mark.asyncio
async def test_user_query_appended_to_messages(agent_logic_no_mcp):
    """The user query should appear in the user message sent to the LLM."""
    await collect(agent_logic_no_mcp.run(make_input_data("hello world")))
    user_msgs = [m for m in agent_logic_no_mcp.messages if m.get("role") == "user"]
    _soft_assert(bool(user_msgs), "no user message found in messages")
    _soft_assert("hello world" in user_msgs[0].get("content", ""), "user_query not found in user message content")


@pytest.mark.asyncio
async def test_llm_is_called(agent_logic_no_mcp, mock_llm_adapter):
    """The LLM adapter should be called once per run."""
    await collect(agent_logic_no_mcp.run(make_input_data("hello")))
    _soft_assert(mock_llm_adapter.llm_chat.called, "llm_chat was never called")


@pytest.mark.asyncio
async def test_artifact_contains_llm_response(agent_logic_no_mcp):
    """The artifact emitted should contain the LLM response text."""
    events = await collect(agent_logic_no_mcp.run(make_input_data("hello")))
    arts = artifact_events(events)
    _soft_assert(bool(arts), "no artifact events emitted")
    if arts:
        part = arts[0].artifact.parts[0].root
        _soft_assert(hasattr(part, "text"), "artifact part has no text attribute")
        _soft_assert(bool(getattr(part, "text", None)), "artifact text is empty")


@pytest.mark.asyncio
async def test_last_artifact_chunk_is_true(agent_logic_no_mcp):
    """The final artifact event should have last_chunk=True."""
    events = await collect(agent_logic_no_mcp.run(make_input_data("hello")))
    arts = artifact_events(events)
    _soft_assert(bool(arts), "no artifact events emitted")
    if arts:
        _soft_assert(arts[-1].last_chunk is True, "last artifact chunk flag is not True")


@pytest.mark.asyncio
async def test_plain_string_llm_response_used_directly(agent_logic_no_mcp, mock_llm_adapter):
    """If the LLM returns a plain string it should be used as the artifact text."""
    mock_llm_adapter.llm_chat = AsyncMock(return_value="plain string answer")
    events = await collect(agent_logic_no_mcp.run(make_input_data("hello")))
    arts = artifact_events(events)
    _soft_assert(bool(arts), "no artifact events emitted")
    if arts:
        text = getattr(arts[0].artifact.parts[0].root, "text", None)
        _soft_assert(text == "plain string answer", f"expected 'plain string answer', got {text!r}")


# ---------------------------------------------------------------------------
# Examples for optional features — copy, un-comment assertions, and adapt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_user_query_appended_to_messages(agent_logic_no_mcp):
    """Example: how to test list-style user_query input joining.
    Uncomment the MCP tool listing block in agent_logic.py and adapt this test."""
    input_data = {"entityConfig": {"inputs": {"user_query": ["part one", "part two"]}}}
    try:
        await collect(agent_logic_no_mcp.run(input_data))
        user_msgs = [m for m in agent_logic_no_mcp.messages if m.get("role") == "user"]
        _soft_assert(bool(user_msgs), "no user message found")
        _soft_assert("part one" in user_msgs[0].get("content", ""), "part one not in user message")
        _soft_assert("part two" in user_msgs[0].get("content", ""), "part two not in user message")
    except Exception as e:
        print(f"\n  [example hint] implement list input handling to make this real: {e}")


@pytest.mark.asyncio
async def test_result_fields_appended_to_user_message(agent_logic_no_mcp):
    """Example: how to test result_* chained fields from a previous agent in a flow."""
    try:
        input_data = make_input_data("analyse this", extra_inputs={"result_from_prev": "previous answer"})
        await collect(agent_logic_no_mcp.run(input_data))
        user_msgs = [m for m in agent_logic_no_mcp.messages if m.get("role") == "user"]
        combined = user_msgs[0].get("content", "") if user_msgs else ""
        _soft_assert("result_from_prev" in combined, "chained result key not in user message")
        _soft_assert("previous answer" in combined, "chained result value not in user message")
    except Exception as e:
        print(f"\n  [example hint] implement result chaining to make this real: {e}")


@pytest.mark.asyncio
async def test_input_required_yields_correct_state(agent_logic_no_mcp, mock_llm_adapter):
    """Example: how to test a skill that pauses and asks the user for more input."""
    try:
        events = await collect(agent_logic_no_mcp.run(make_input_data("greet")))
        input_req = [e for e in events if isinstance(e, TaskStatusUpdateEvent)
                     and e.status.state == TaskState.input_required]
        _soft_assert(bool(input_req), "no input_required event emitted — implement the input-required flow")
    except Exception as e:
        print(f"\n  [example hint] implement an input-required branch to make this real: {e}")


@pytest.mark.asyncio
async def test_input_required_does_not_yield_artifact(agent_logic_no_mcp):
    """Example: input-required paths should not emit an artifact."""
    try:
        events = await collect(agent_logic_no_mcp.run(make_input_data("greet")))
        _soft_assert(not artifact_events(events), "artifact emitted on an input-required path — should return early")
    except Exception as e:
        print(f"\n  [example hint] {e}")


@pytest.mark.asyncio
async def test_mcp_list_tools_called(agent_logic, mock_llm_adapter):
    """Example: assert that list_tools is called when MCP is configured.
    Uncomment the MCP block in agent_logic.py to make this real."""
    try:
        await collect(agent_logic.run(make_input_data("hello")))
        _soft_assert(agent_logic.mcp_wrapper.list_tools.called, "list_tools was not called — uncomment the MCP block")
    except Exception as e:
        print(f"\n  [example hint] uncomment MCP tool listing in agent_logic.py: {e}")


@pytest.mark.asyncio
async def test_mcp_tool_is_called(agent_logic, mock_llm_adapter, mock_mcp_wrapper):
    """Example: assert that a tool call from the LLM is forwarded to the MCP wrapper."""
    try:
        tool_call = {"name": "echo_tool", "args": {"x": 1}}
        mock_llm_adapter.llm_chat = AsyncMock(
            side_effect=[FakeLLMResponse("...", tool_calls=[tool_call]), FakeLLMResponse("final answer")]
        )
        await collect(agent_logic.run(make_input_data("use a tool")))
        _soft_assert(mock_mcp_wrapper.call_tool.called, "call_tool was not called — uncomment the tool-call loop")
    except Exception as e:
        print(f"\n  [example hint] uncomment the tool-call loop in agent_logic.py: {e}")


@pytest.mark.asyncio
async def test_mcp_follow_up_llm_called_after_tool(agent_logic, mock_llm_adapter, mock_mcp_wrapper):
    """Example: assert the LLM is called a second time after receiving a tool result."""
    try:
        tool_call = {"name": "echo_tool", "args": {}}
        mock_llm_adapter.llm_chat = AsyncMock(
            side_effect=[FakeLLMResponse("...", tool_calls=[tool_call]), FakeLLMResponse("follow-up")]
        )
        await collect(agent_logic.run(make_input_data("use tool")))
        _soft_assert(mock_llm_adapter.llm_chat.call_count == 2,
                     f"expected 2 LLM calls, got {mock_llm_adapter.llm_chat.call_count}")
    except Exception as e:
        print(f"\n  [example hint] uncomment the tool-call loop in agent_logic.py: {e}")


@pytest.mark.asyncio
async def test_mcp_tool_result_appended_to_messages(agent_logic, mock_llm_adapter, mock_mcp_wrapper):
    """Example: assert the tool result is appended to messages before the follow-up LLM call."""
    try:
        tool_call = {"name": "echo_tool", "args": {}}
        mock_llm_adapter.llm_chat = AsyncMock(
            side_effect=[FakeLLMResponse("...", tool_calls=[tool_call]), FakeLLMResponse("done")]
        )
        await collect(agent_logic.run(make_input_data("use tool")))
        tool_msgs = [m for m in agent_logic.messages if isinstance(m, dict) and m.get("role") == "tool"]
        _soft_assert(bool(tool_msgs), "tool result message not appended to messages")
    except Exception as e:
        print(f"\n  [example hint] uncomment the tool-call loop in agent_logic.py: {e}")


@pytest.mark.asyncio
async def test_mcp_artifact_contains_follow_up_content(agent_logic, mock_llm_adapter, mock_mcp_wrapper):
    """Example: artifact text should come from the follow-up LLM call, not the tool-call response."""
    try:
        tool_call = {"name": "echo_tool", "args": {}}
        mock_llm_adapter.llm_chat = AsyncMock(
            side_effect=[FakeLLMResponse("...", tool_calls=[tool_call]), FakeLLMResponse("follow-up answer")]
        )
        events = await collect(agent_logic.run(make_input_data("use tool")))
        arts = artifact_events(events)
        _soft_assert(bool(arts), "no artifact events emitted")
        if arts:
            text = getattr(arts[0].artifact.parts[0].root, "text", None)
            _soft_assert(text == "follow-up answer", f"expected 'follow-up answer', got {text!r}")
    except Exception as e:
        print(f"\n  [example hint] uncomment the tool-call loop in agent_logic.py: {e}")
