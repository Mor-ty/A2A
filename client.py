from uuid import uuid4
import asyncio
import httpx
from colorama import Fore, Style
import json
from typing import Any

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (MessageSendParams, TaskArtifactUpdateEvent, Message, TaskStatusUpdateEvent,
                       Task, SendStreamingMessageRequest, JSONRPCErrorResponse, TaskState, TextPart, DataPart, FilePart)
from agent_card import public_agent_card


def build_message_payload(parts, task_id: str | None = None, context_id: str | None = None) -> dict[str, Any]:
    return {
        "message": {
            "role": "user",
            "parts": parts,
            "message_id": uuid4().hex,
            "metadata": {"execution_id": "", "experience_id": "",
                         "session_id": ""},
            **({"task_id": task_id} if task_id else {}),
            **({"context_id": context_id} if context_id else {}),
        }
    }


async def handle_streaming_message(parts, client: A2AClient, task_id: str | None = None, context_id: str | None = None):
    # print(build_message_payload(parts, task_id, context_id))
    request = SendStreamingMessageRequest(
        id=str(uuid4()),
        params=MessageSendParams(**build_message_payload(parts, task_id, context_id))
    )

    async for response in client.send_message_streaming(request):
        root = response.root
        if isinstance(root, JSONRPCErrorResponse):
            print(Fore.LIGHTMAGENTA_EX + f"[Error] Agent: {root.error}" + Style.RESET_ALL)
        if hasattr(root, 'result') and response.root.result:
            event = response.root.result
            if isinstance(event, Message):
                print(Fore.LIGHTCYAN_EX + f" Agent: {event.parts[0].root.text}" + Style.RESET_ALL)
            if isinstance(event, Task):
                print(f"Agent: Task initialised with id - {event.id}")
                continue
            if isinstance(event, TaskStatusUpdateEvent):
                print(Fore.LIGHTBLUE_EX + f"Agent [status]: {event.status.state.name}")
                if event.status.message:
                    if isinstance(event.status.message.parts[0].root, TextPart):
                        print(f"{event.status.message.parts[0].root.text}" + Style.RESET_ALL)
                    elif isinstance(event.status.message.parts[0].root, DataPart):
                        print(f"{json.dumps(event.status.message.parts[0].root.data, indent=4)}" + Style.RESET_ALL)
                    elif isinstance(event.status.message.parts[0].root, FilePart):
                        file_info = event.status.message.parts[0].root.file
                        file_name = getattr(file_info, 'name', 'unknown_file')
                        print(f"File received: {file_name}" + Style.RESET_ALL)

            if isinstance(event, TaskArtifactUpdateEvent):
                root = event.artifact.parts[0].root
                if hasattr(root, "data"):
                    print(Fore.LIGHTCYAN_EX + f"Agent [artifact]:{json.dumps(root.data, indent=4)}" + Style.RESET_ALL)
                elif hasattr(root, "text"):
                    print(Fore.LIGHTCYAN_EX + f"Agent [artifact]:{event.artifact.parts[0].root.text}" + Style.RESET_ALL)
                elif hasattr(root, "file"):
                    file_info = root.file
                    file_name = getattr(file_info, 'name', 'unknown_file')
                    file_artifact = {
                        "result": {
                            "name": file_name,
                            "mimeType": getattr(file_info, 'mime_type', 'unknown'),
                            "bytes": getattr(file_info, 'bytes', '')
                        }
                    }
                    print(Fore.LIGHTCYAN_EX + f"Agent [artifact] {file_name}: {json.dumps(file_artifact, indent=4)}" + Style.RESET_ALL)

        elif response.root.error:
            print(Fore.LIGHTMAGENTA_EX + "Agent Error:", response.root.error.message + Style.RESET_ALL)

async def interactive_loop(client: A2AClient):
    context_id = "12345"

    # 1. Configuration: input-config.json only
    with open("input-config.json", "r", encoding="utf-8") as f:
        config_data = json.load(f)
    task_id = config_data.get("taskId", "")
    await handle_streaming_message(
        client=client,
        parts=[{"kind": "data", "data": config_data}],
        context_id=context_id,
        task_id=task_id,
    )

    # 2. Message: input-message.json only (files are inside entityConfig.inputs as file parts)
    with open("input-message.json", "r", encoding="utf-8") as f:
        message_data = json.load(f)
    task_id = message_data.get("taskId", "") or task_id
    await handle_streaming_message(
        client=client,
        parts=[{"kind": "data", "data": message_data}],
        context_id=context_id,
        task_id=task_id,
    )


async def main():
    timeout = httpx.Timeout(300.0, read=300.0)
    async with httpx.AsyncClient(timeout=timeout) as httpx_client:
        client = A2AClient(httpx_client=httpx_client, agent_card=public_agent_card)
        await interactive_loop(client=client)

if __name__ == '__main__':
    asyncio.run(main())



