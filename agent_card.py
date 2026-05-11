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
    name="Lens",
    description=(
        "Lens automation suite — (1) decomposes Excel test specs into state steps, "
        "(2) builds deduplicated layered flow graphs as interactive HTML."
    ),
    url=f"http://{server}:{port}/",
    version="2026.5",
    provider=AgentProvider(
        organization="Studio X",
        url="my_agent.example.com",
    ),
    documentation_url="https://docs.example.com",
    icon_url=f"https://{server}/ApiGateWay-Uat/Images/StudioX/Studio X 4.svg",
    protocol_version="0.2.5",
    default_input_modes=["text", "data", "file"],
    default_output_modes=["text", "data", "file"],
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
            id="lens_tc_decompose_skill",
            name="TC Decomposer (Agent 1)",
            description=(
                "Upload an Excel workbook of automation test cases (columns such as TC_ID, "
                "TC_Name, TC_Description). Returns a structured workbook: one row per step with "
                "initial_state and final_state for each test case."
            ),
            tags=["lens", "automation", "excel", "test-cases", "decomposition"],
            examples=["Upload lens_test_cases.xlsx and run decomposition."],
            input_modes=["text", "data", "file"],
            output_modes=["text", "file", "data"],
        ),
        AgentSkill(
            id="lens_graph_visualiser_skill",
            name="Graph visualiser (Agent 2)",
            description=(
                "Consumes Agent 1 decomposition Excel (initial_state / final_state rows). "
                "Merges near-duplicate states conservatively, assigns depth-based layers, "
                "and returns an interactive vis-network HTML graph across all test cases."
            ),
            tags=["lens", "graph", "visualisation", "deduplication", "flow"],
            examples=["Upload lens_decomposed_steps.xlsx from Agent 1 and generate the graph."],
            input_modes=["text", "data", "file"],
            output_modes=["text", "file", "data"],
        ),
    ],
    additional_interfaces=[],
    preferred_transport="jsonrpc",
    supports_authenticated_extended_card=True,
    security=[{"apiKey": []}],
    security_schemes=None,
)

required_blueprint_keys_list = []

skill_input_enrichments = {
    "lens_tc_decompose_skill": SkillInputEnrichment(
        parameters=[
            SkillInputParameter(
                name="chatInput",
                display_name="Intent",
                data_type=DataType.STRING,
                description="Short description of what to do (used for guardrails).",
                required=False,
                sample="Decompose uploaded automation test cases workbook.",
                default_value=None,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="workbook",
                display_name="Test cases Excel",
                data_type=DataType.FILE,
                description="Excel file (.xlsx) with test cases; must include a TC_Description column.",
                required=True,
                sample="test_cases.xlsx",
                default_value=None,
                source_priority=[DataSource.USER],
            ),
        ]
    ),
    "lens_graph_visualiser_skill": SkillInputEnrichment(
        parameters=[
            SkillInputParameter(
                name="chatInput",
                display_name="Intent",
                data_type=DataType.STRING,
                description="Short description for guardrails.",
                required=False,
                sample="Build deduplicated flow graph from decomposition workbook.",
                default_value=None,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="decomposition_workbook",
                display_name="Decomposition Excel (Agent 1 output)",
                data_type=DataType.FILE,
                description="The .xlsx produced by TC Decomposer with initial_state and final_state columns.",
                required=True,
                sample="lens_decomposed_steps.xlsx",
                default_value=None,
                source_priority=[DataSource.USER],
            ),
        ]
    ),
}

skill_output_enrichments = {
    "lens_tc_decompose_skill": SkillOutputEnrichment(
        outputs=[
            SkillOutputParameter(
                name="summary",
                data_type=DataType.STRING,
                description="Markdown summary of decomposition counts.",
                required=True,
                sample="Found 12 test cases; produced 48 step rows.",
            ),
            SkillOutputParameter(
                name="decomposed_workbook",
                data_type=DataType.FILE,
                description="Excel file with columns tc_id, step, initial_state, final_state, …",
                required=True,
                sample="lens_decomposed_steps.xlsx",
            ),
        ]
    ),
    "lens_graph_visualiser_skill": SkillOutputEnrichment(
        outputs=[
            SkillOutputParameter(
                name="summary",
                data_type=DataType.STRING,
                description="Markdown summary: node/edge counts, merge stats.",
                required=True,
                sample="Merged 120 labels → 45 nodes; 210 edges.",
            ),
            SkillOutputParameter(
                name="flow_graph_html",
                data_type=DataType.FILE,
                description="Interactive vis-network HTML (offline-capable with CDN script).",
                required=True,
                sample="lens_flow_graph.html",
            ),
        ]
    ),
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
            "You are **Lens**.\n"
            "**Agent 1 (decompose):** You receive batches of test-case metadata with `tc_description`. "
            "Output strict JSON only (no markdown fences):\n"
            '{"test_cases":[{"tc_id":"...","asset_id":"...","app_id":"...","tc_name":"...",'
            '"row_index":<number>,"steps":['
            '{"step":1,"initial_state":"<short>","final_state":"<short>"}]}]}\n'
            "Rules: ordered steps; initial_state of step k+1 should follow step k; concise UI labels; "
            "no invented features; preserve ids.\n"
            "**Agent 2 (graph):** When asked for synonym pairs, output only JSON "
            '`{"equivalent_pairs":[{"a":"...","b":"..."}]}` — merge only undeniable duplicate states; '
            "when in doubt omit pairs.\n"
        ),
        "skill_input_enrichments": skill_input_enrichments,
        "skill_output_enrichments": skill_output_enrichments,
    }
)
