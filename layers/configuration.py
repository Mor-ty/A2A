import logging
from agentic_os_infra.core.layers.configuration_base import ConfigurationBase

logger = logging.getLogger(__name__)

class ConfigurationLayer(ConfigurationBase):
    def __init__(self, blueprint, extended_agent_card, monitoring_metadata):
        super().__init__(blueprint, extended_agent_card, monitoring_metadata)

    async def custom(self, mcp_wrapper):
        pass