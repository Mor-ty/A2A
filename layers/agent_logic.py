import json
import logging
from typing import AsyncGenerator, Optional, Type

from pydantic import BaseModel
from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent

from agentic_os_infra.core.layers.agent_logic_base import AgentLogicBase

logger = logging.getLogger(__name__)

# OpenAI-style function definitions for bind_tools
CALCULATOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add",
            "description": "Return the sum of two numbers (a + b).",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First operand."},
                    "b": {"type": "number", "description": "Second operand."},
                },
                "required": ["a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subtract",
            "description": "Return a minus b (a - b).",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "Minuend."},
                    "b": {"type": "number", "description": "Subtrahend."},
                },
                "required": ["a", "b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "multiply",
            "description": "Return the product of two numbers (a * b).",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First factor."},
                    "b": {"type": "number", "description": "Second factor."},
                },
                "required": ["a", "b"],
            },
        },
    },
]


class _ToolResult:
    """Thin wrapper expected by create_tool_message (content as string)."""

    def __init__(self, data: str):
        self.data = data


def _trace_payload(phase: str, **fields: object) -> dict:
    """Structured status payload for UIs (e.g. Gradio) to render thinking / tools."""
    return {"kind": "trace", "phase": phase, **fields}


def _reasoning_and_visible_text(response: object) -> tuple[str, str]:
    """
    Best-effort extraction of model reasoning vs visible text from an AIMessage
    (OpenAI / Azure reasoning models may use block lists or additional_kwargs).
    """
    reasoning_parts: list[str] = []
    visible_parts: list[str] = []

    if isinstance(response, str):
        return "", response.strip()

    content = getattr(response, "content", None)
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                visible_parts.append(str(block))
                continue
            btype = block.get("type", "")
            if btype == "reasoning":
                text = block.get("reasoning") or block.get("text") or ""
                if isinstance(text, str) and text.strip():
                    reasoning_parts.append(text.strip())
                elif isinstance(block.get("summary"), list):
                    reasoning_parts.append(json.dumps(block.get("summary"), ensure_ascii=False))
            elif btype in ("text", "output_text"):
                t = block.get("text", "")
                if t:
                    visible_parts.append(str(t))
            else:
                visible_parts.append(json.dumps(block, ensure_ascii=False))
    elif isinstance(content, str) and content.strip():
        visible_parts.append(content.strip())

    ak = getattr(response, "additional_kwargs", None) or {}
    rc = ak.get("reasoning_content")
    if isinstance(rc, str) and rc.strip():
        reasoning_parts.append(rc.strip())
    rdict = ak.get("reasoning")
    if isinstance(rdict, dict):
        for key in ("text", "reasoning", "content"):
            val = rdict.get(key)
            if isinstance(val, str) and val.strip():
                reasoning_parts.append(val.strip())
                break

    return "\n\n".join(reasoning_parts), "\n".join(visible_parts)


class AgentLogicLayer(AgentLogicBase):
    def __init__(self, mcp_wrapper, llm_adapter, monitoring_metadata, result_model: Optional[Type[BaseModel]] = None):
        super().__init__(mcp_wrapper, llm_adapter, monitoring_metadata, result_model)

    def _add(self, a: float, b: float) -> str:
        return str(a + b)

    def _subtract(self, a: float, b: float) -> str:
        return str(a - b)

    def _multiply(self, a: float, b: float) -> str:
        return str(a * b)

    async def _execute_tool(self, name: str, args: dict) -> _ToolResult:
        a = float(args.get("a", 0))
        b = float(args.get("b", 0))
        if name == "add":
            result = self._add(a, b)
        elif name == "subtract":
            result = self._subtract(a, b)
        elif name == "multiply":
            result = self._multiply(a, b)
        else:
            result = f"Unknown tool: {name}"
        return _ToolResult(result)

    async def run(
        self,
        input_data: dict,
        context_id: str = "",
        task_id: str = "",
    ) -> AsyncGenerator[TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:

        yield self.status_response(content="Calculator agent started")

        inputs = input_data.get("entityConfig", {}).get("inputs", {})
        user_query = inputs.get("user_query", "")

        if not self.messages:
            self.messages = [{"role": "system", "content": self.llm_adapter.system_prompt}]

        self.messages.append({"role": "user", "content": user_query})

        yield self.status_response(content="Running LLM with calculator tools")

        self.llm_adapter.client = self.llm_adapter.client.bind_tools(CALCULATOR_TOOLS)

        response = await self.llm_adapter.llm_chat(self.messages)
        reasoning, visible = _reasoning_and_visible_text(response)
        if reasoning:
            yield self.status_response(content=_trace_payload("thinking", text=reasoning))
        if visible:
            yield self.status_response(content=_trace_payload("assistant_text", text=visible))

        max_iterations = 10
        iteration = 0
        while True:
            tool_calls = getattr(response, "tool_calls", [])
            if not tool_calls or iteration >= max_iterations:
                break
            self.messages.append(response)
            for call in tool_calls:
                tool_name = call.get("name") if isinstance(call, dict) else call.function.name
                tool_args = call.get("args") if isinstance(call, dict) else call.function.arguments
                if isinstance(tool_args, str):
                    tool_args = json.loads(tool_args)
                yield self.status_response(
                    content=_trace_payload(
                        "tool_call",
                        tool=tool_name,
                        arguments=tool_args,
                    )
                )
                tool_result = await self._execute_tool(tool_name, tool_args)
                yield self.status_response(
                    content=_trace_payload(
                        "tool_result",
                        tool=tool_name,
                        result=tool_result.data,
                    )
                )
                self.messages.append(self.llm_adapter.create_tool_message(call, tool_result))
            response = await self.llm_adapter.llm_chat(self.messages)
            reasoning, visible = _reasoning_and_visible_text(response)
            if reasoning:
                yield self.status_response(content=_trace_payload("thinking", text=reasoning))
            if visible:
                yield self.status_response(content=_trace_payload("assistant_text", text=visible))
            iteration += 1

        if isinstance(response, str):
            response_text = response.strip()
        else:
            _r_last, visible_last = _reasoning_and_visible_text(response)
            raw = getattr(response, "content", "")
            if isinstance(raw, list):
                response_text = visible_last or json.dumps(raw, ensure_ascii=False)
            elif isinstance(raw, str) and raw.strip():
                response_text = raw.strip()
            else:
                response_text = visible_last or _r_last or ""

        yield self.artifact_response(content=response_text, last_chunk=True)
