import pytest
from unittest.mock import AsyncMock

from tests.conftest import make_input_data, FakeLLMResponse
from a2a.types import TaskArtifactUpdateEvent
from agent_card import skill_input_enrichments, skill_output_enrichments
from agentic_os_infra.core.input_output_standard.skill_input_output_standard import DataType


async def collect(gen) -> list:
    events = []
    async for e in gen:
        events.append(e)
    return events


def test_skill_input_enrichment_present_and_sample_type():
    # Ensure input enrichment for skill '123abc' exists and sample is a string
    assert '123abc' in skill_input_enrichments, "skill '123abc' input enrichment missing"
    inp = skill_input_enrichments['123abc']
    params = inp.parameters
    assert params, "No parameters defined for skill '123abc'"
    p = params[0]
    assert p.data_type == DataType.STRING, "Expected input data_type to be DataType.STRING"
    assert isinstance(p.sample, str), "Input sample must be a string for DataType.STRING"


@pytest.mark.asyncio
async def test_agent_logic_returns_string_artifact_for_skill_input(agent_logic_no_mcp, mock_llm_adapter):
    # Prepare a mocked LLM response that matches the declared output enrichment (STRING)
    mock_response_text = "The weather today is sunny."
    mock_llm_adapter.llm_chat = AsyncMock(return_value=FakeLLMResponse(mock_response_text))

    # Use the sample input from the skill input enrichment
    sample_input = skill_input_enrichments['123abc'].parameters[0].sample
    input_data = make_input_data(sample_input)

    events = await collect(agent_logic_no_mcp.run(input_data))
    arts = [e for e in events if isinstance(e, TaskArtifactUpdateEvent)]
    assert arts, "No artifact events emitted by AgentLogicLayer"

    part = arts[0].artifact.parts[0].root
    # For DataType.STRING we expect text attribute to be a string
    assert hasattr(part, 'text'), "Artifact root missing 'text' attribute"
    assert isinstance(part.text, str), f"Artifact text must be str, got {type(part.text)}"
    assert part.text == mock_response_text, "Artifact text does not match mocked LLM response"

    # Also verify the declared output enrichment expects a STRING
    out = skill_output_enrichments['123abc']
    out_param = out.outputs[0]
    assert out_param.data_type == DataType.STRING, "Declared output data_type is not DataType.STRING"

