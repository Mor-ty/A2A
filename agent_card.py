from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    AgentExtension,
    AgentProvider,
)
from dotenv import load_dotenv
import os
from datetime import datetime
from agentic_os_infra.core.extended_agent_card import ExtendedAgentCard
from agentic_os_infra.core.input_output_standard.skill_input_output_standard import (
    SkillOutputEnrichment,
    SkillOutputParameter,
    SkillInputEnrichment,
    SkillInputParameter,
    DataType,
    DataSource,
)

load_dotenv()
server = os.getenv("HOST_NAME", "localhost")
port = int(os.getenv("PORT", "9996"))

public_agent_card = AgentCard(
    name="Calculator Agent",
    description=(
        "A simple A2A agent that answers arithmetic questions using three tools: "
        "add, subtract, and multiply."
    ),
    url=f"http://{server}:{port}/",
    version="2026.4",
    provider=AgentProvider(
        organization="Studio X",
        url="my_agent.example.com",
    ),
    documentation_url="https://docs.example.com",
    icon_url=f"https://{server}/ApiGateWay-Uat/Images/StudioX/Studio X 4.svg",
    protocol_version="0.2.5",
    default_input_modes=["text", "data"],
    default_output_modes=["text", "data"],
    capabilities=AgentCapabilities(
        streaming=True,
        push_notifications=True,
        state_transition_history=True,
        extensions=[
            AgentExtension(
                uri="example-extension",
                description="Example extension",
                required=False,
                params=None,
            )
        ],
    ),
    skills=[
        AgentSkill(
            id="calculator_skill",
            name="Calculator",
            description=(
                "Ask for sums, differences, or products. The agent uses tools to compute exact numeric results."
            ),
            tags=["math", "calculator", "arithmetic", "tools"],
            examples=[
                "What is 17 plus 25?",
                "Subtract 3.5 from 10.",
                "Multiply 12 by 8.",
                "What is (42 - 7) times 2? Use the tools step by step.",
            ],
            input_modes=["text", "data"],
            output_modes=["text"],
        )
    ],
    additional_interfaces=[],
    preferred_transport="jsonrpc",
    supports_authenticated_extended_card=True,
    security=[{"apiKey": []}],
    security_schemes=None,
)

required_blueprint_keys_list = []

skill_input_enrichments = {
    "calculator_skill": SkillInputEnrichment(
        parameters=[
            SkillInputParameter(
                name="user_query",
                display_name="Math question",
                data_type=DataType.STRING,
                description="A natural-language arithmetic question or expression to evaluate with tools.",
                required=True,
                sample="What is 144 divided into adding 12 and 12? Actually just multiply 12 by 12.",
                default_value=None,
                source_priority=[DataSource.USER],
            )
        ]
    )
}

skill_output_enrichments = {
    "calculator_skill": SkillOutputEnrichment(
        outputs=[
            SkillOutputParameter(
                name="result",
                data_type=DataType.STRING,
                description="The assistant's answer, including numeric results from tool calls.",
                required=True,
                sample="12 × 12 = 144.",
            )
        ]
    )
}

extended_agent_card = ExtendedAgentCard.model_validate(public_agent_card.model_dump())
extended_agent_card = extended_agent_card.model_copy(
    update={
        "id": "f93b7028-2838-4e44-9e58-975ad6d65b21",
        "required_blueprint_keys": required_blueprint_keys_list,
        "last_updated": datetime.now().strftime("%d/%m/%y %H:%M"),
        "value": "",
        "active": True,
        "agentic_os_infra": True,
        "send_output_from_config_mode": False,
        "system_prompt": (
            "You are a calculator assistant. You have exactly three tools:\n"
            "- add(a, b) — returns a + b\n"
            "- subtract(a, b) — returns a - b\n"
            "- multiply(a, b) — returns a * b\n\n"
            "For any arithmetic the user asks, call the appropriate tool(s). "
            "You may chain tools for multi-step problems. "
            "Reply with a short, clear final answer and show the numbers you used."
        ),
        "skill_input_enrichments": skill_input_enrichments,
        "skill_output_enrichments": skill_output_enrichments,
    }
)
