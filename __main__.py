from agentic_os_infra.core.config_store.data_to_persist_store import SQLiteContextDataStore
from starlette.responses import JSONResponse
from starlette.routing import Route

from agentic_os_infra.executor.agent_executor import (
    MyAgentExecutor,  # type: ignore[import-untyped]
)
from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from agent_card import *
import logging
import os
import uvicorn

from layers.configuration import ConfigurationLayer
from layers.guardrails import GuardrailsLayer
from layers.agent_logic import AgentLogicLayer
from layers.evaluation import EvaluationLayer
from layers.compliance import ComplianceLayer
from agentic_os_infra.core.config_store.config_store_class import SQLiteConfigStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)

def create_app():
    db_path = os.getenv("CONFIG_DB", "config_store.db")
    shared_store = SQLiteConfigStore(db_path)
    context_data_store = SQLiteContextDataStore(db_path)

    request_handler = DefaultRequestHandler(
        agent_executor=MyAgentExecutor(configuration_layer=ConfigurationLayer,
                                       guardrails_layer=GuardrailsLayer,
                                       logic_layer=AgentLogicLayer,
                                       evaluation_layer=EvaluationLayer,
                                       compliance_layer=ComplianceLayer,
                                       extended_agent_card=extended_agent_card,
                                       config_store=shared_store, context_data_store=context_data_store),
    task_store=InMemoryTaskStore(),)


    server = A2AStarletteApplication(agent_card=extended_agent_card,
                                     http_handler=request_handler,
                                     extended_agent_card=extended_agent_card,
                                     )

    app = server.build()

    app.routes.append(
        Route(
            "/extended-agent-card",
            lambda request: JSONResponse(extended_agent_card.model_dump()),
            methods=["GET"],
            name="extended_agent_card"
        )
    )
    logger.info("A2A app created successfully.")
    return app


if __name__ == '__main__':
    host = "0.0.0.0"
    port = int(os.getenv("PORT", "9996"))
    workers = int(os.getenv("UVICORN_WORKERS", "1"))
    reload_flag = os.getenv("UVICORN_RELOAD", "false").lower() in ("1", "true", "yes")
    if reload_flag and workers > 1:
        workers = 1

    uvicorn.run(
        "__main__:create_app",
        host=host,
        port=port,
        workers=workers,
        factory=True,
        reload=reload_flag,
        timeout_keep_alive=120,
    )