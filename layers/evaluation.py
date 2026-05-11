import logging
from agentic_os_infra.core.layers.evaluation_base import EvaluationBase
from agentic_os_infra.core.utils import *

logger = logging.getLogger(__name__)

class EvaluationLayer(EvaluationBase):
    def __init__(self, mcp_wrapper, monitoring_metadata):
        super().__init__(mcp_wrapper, monitoring_metadata)


    async def custom(self, llm_output: str) -> bool:
        return True
