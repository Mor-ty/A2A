import logging
from agentic_os_infra.core.layers.guardrails_base import GuardrailsBase
logger = logging.getLogger(__name__)
from agentic_os_infra.core.utils import *


class GuardrailsLayer(GuardrailsBase):
    def __init__(self, mcp_wrapper, monitoring_metadata):
        super().__init__(mcp_wrapper, monitoring_metadata)

    async def custom(self, user_input)-> bool:
            return True
