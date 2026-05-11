import json
import logging
from typing import AsyncGenerator, Optional, Type

from pydantic import BaseModel
from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent

from agentic_os_infra.core.layers.agent_logic_base import AgentLogicBase

from layers.lens_graph_visualiser import run_lens_graph_visualiser
from layers.lens_tc_decompose import run_lens_tc_decompose

logger = logging.getLogger(__name__)

DECOMPOSE_SKILL_ID = "lens_tc_decompose_skill"
GRAPH_SKILL_ID = "lens_graph_visualiser_skill"


def _trace_payload(phase: str, **fields: object) -> dict:
    return {"kind": "trace", "phase": phase, **fields}


class AgentLogicLayer(AgentLogicBase):
    def __init__(self, mcp_wrapper, llm_adapter, monitoring_metadata, result_model: Optional[Type[BaseModel]] = None):
        super().__init__(mcp_wrapper, llm_adapter, monitoring_metadata, result_model)

    async def run(
        self,
        input_data: dict,
        context_id: str = "",
        task_id: str = "",
    ) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:

        skill_id = (input_data.get("entityConfig") or {}).get("skillId", "")

        if skill_id == DECOMPOSE_SKILL_ID:
            async for ev in run_lens_tc_decompose(self, input_data):
                yield ev
            return

        if skill_id == GRAPH_SKILL_ID:
            async for ev in run_lens_graph_visualiser(self, input_data):
                yield ev
            return

        yield self.status_response(content=_trace_payload("lens_error", message=f"Unknown skill: {skill_id}"))
        yield self.artifact_response(
            content=f"Unknown skill. Use `{DECOMPOSE_SKILL_ID}` or `{GRAPH_SKILL_ID}`.",
            last_chunk=True,
        )
