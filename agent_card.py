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
        "(2) builds deduplicated layered flow graphs as interactive HTML, "
        "(3) n×n cosine similarity matrices from state chains, "
        "(4) disjoint-set clustering from those matrices (sim > τ)."
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
                "and returns an interactive vis-network HTML graph across all test cases. "
                "Optionally chains to Agents 3–4 over A2A (similarity matrix then clusters)."
            ),
            tags=["lens", "graph", "visualisation", "deduplication", "flow"],
            examples=["Upload lens_decomposed_steps.xlsx from Agent 1 and generate the graph."],
            input_modes=["text", "data", "file"],
            output_modes=["text", "file", "data"],
        ),
        AgentSkill(
            id="lens_tc_similarity_skill",
            name="TC similarity (Agent 3)",
            description=(
                "Builds an n×n cosine-similarity matrix between test cases from their connected states. "
                "**Automated A2A pipeline:** consumes the **Agent 1 decomposition Excel** only (state chains). "
                "Optional extra: Agent 2 graph HTML for Tab 3 manual enrich only. "
                "TF–IDF vectorisation; diagonal forced to 1; thresholded pair list (default 0.8). "
                "May chain Agent 4 over A2A for clustering."
            ),
            tags=["lens", "similarity", "embeddings", "cosine", "matrix", "excel"],
            examples=["Upload lens_decomposed_steps.xlsx and request similarity_matrix.xlsx."],
            input_modes=["text", "data", "file"],
            output_modes=["text", "file", "data"],
        ),
        AgentSkill(
            id="lens_tc_cluster_skill",
            name="TC clustering (Agent 4)",
            description=(
                "Reads the Agent 3 similarity-matrix workbook and merges test cases into disjoint groups: "
                "union TC_i and TC_j when sim(i,j) > τ (strict). Outputs per-TC cluster_id and summary sheet."
            ),
            tags=["lens", "clustering", "union-find", "similarity"],
            examples=["Upload lens_tc_similarity_matrix.xlsx from Agent 3 with τ = 0.8."],
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
            SkillInputParameter(
                name="lens_chain_agent2",
                display_name="Chain Agent 2 after decomposition",
                data_type=DataType.BOOL,
                description="When true, forwards decomposition workbook to lens_graph_visualiser_skill over HTTP A2A.",
                required=False,
                sample=True,
                default_value=True,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="lens_chain_agent3",
                display_name="Chain Agent 3 (similarity)",
                data_type=DataType.BOOL,
                description="After Agent 2 graph: A2A to similarity using Agent 1 workbook only. If Agent 2 is off: A2A to similarity directly.",
                required=False,
                sample=True,
                default_value=True,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="similarity_threshold",
                display_name="Similarity pair threshold (chain)",
                data_type=DataType.NUMBER,
                description="Similarity pair threshold for chained Agent 3 (with or without Agent 2; default 0.8).",
                required=False,
                sample=0.8,
                default_value=0.8,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="lens_chain_agent4",
                display_name="Chain Agent 4 after similarity",
                data_type=DataType.BOOL,
                description="Passed through so chained Agent 3 runs lens_tc_cluster_skill over A2A on the matrix.",
                required=False,
                sample=True,
                default_value=True,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="cluster_threshold",
                display_name="Cluster merge threshold τ",
                data_type=DataType.NUMBER,
                description="Agent 4 merges TCs when sim > τ (default: same as similarity_threshold).",
                required=False,
                sample=0.8,
                default_value=0.8,
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
            SkillInputParameter(
                name="lens_chain_agent3",
                display_name="Chain Agent 3 after graph",
                data_type=DataType.BOOL,
                description="When true, runs lens_tc_similarity_skill over HTTP A2A using **Agent 1 decomposition workbook** only.",
                required=False,
                sample=True,
                default_value=True,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="similarity_threshold",
                display_name="Similarity pair threshold",
                data_type=DataType.NUMBER,
                description="Pairs with cosine similarity ≥ this value appear in pairs_ge_threshold (default 0.8).",
                required=False,
                sample=0.8,
                default_value=0.8,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="lens_chain_agent4",
                display_name="Chain Agent 4 after similarity",
                data_type=DataType.BOOL,
                description="When true, chained Agent 3 forwards the matrix to lens_tc_cluster_skill over A2A.",
                required=False,
                sample=True,
                default_value=True,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="cluster_threshold",
                display_name="Cluster merge threshold τ",
                data_type=DataType.NUMBER,
                description="Agent 4: union TCs when sim > τ (defaults to similarity_threshold).",
                required=False,
                sample=0.8,
                default_value=0.8,
                source_priority=[DataSource.USER],
            ),
        ]
    ),
    "lens_tc_similarity_skill": SkillInputEnrichment(
        parameters=[
            SkillInputParameter(
                name="chatInput",
                display_name="Intent",
                data_type=DataType.STRING,
                description="Short description for guardrails.",
                required=False,
                sample="Cosine similarity matrix between test cases from state chains.",
                default_value=None,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="decomposition_workbook",
                display_name="Decomposition Excel (preferred)",
                data_type=DataType.FILE,
                description="Agent 1 step table: tc_id, step, initial_state, final_state (same file as Agent 2 input).",
                required=False,
                sample="lens_decomposed_steps.xlsx",
                default_value=None,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="graph_html",
                display_name="Agent 2 graph HTML (optional)",
                data_type=DataType.FILE,
                description="Lens flow graph HTML; per-TC states inferred from vis-network node tooltips when Excel is absent.",
                required=False,
                sample="lens_flow_graph.html",
                default_value=None,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="similarity_threshold",
                display_name="Pair-report threshold",
                data_type=DataType.NUMBER,
                description="Pairs with cosine similarity ≥ this value are listed (default 0.8).",
                required=False,
                sample=0.8,
                default_value=0.8,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="lens_chain_agent4",
                display_name="Chain Agent 4 after matrix",
                data_type=DataType.BOOL,
                description="When true, runs lens_tc_cluster_skill over HTTP A2A on this skill’s matrix output.",
                required=False,
                sample=True,
                default_value=True,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="cluster_threshold",
                display_name="Cluster merge threshold τ",
                data_type=DataType.NUMBER,
                description="Merge TCs when sim > τ (default: similarity_threshold).",
                required=False,
                sample=0.8,
                default_value=0.8,
                source_priority=[DataSource.USER],
            ),
        ]
    ),
    "lens_tc_cluster_skill": SkillInputEnrichment(
        parameters=[
            SkillInputParameter(
                name="chatInput",
                display_name="Intent",
                data_type=DataType.STRING,
                description="Short description for guardrails.",
                required=False,
                sample="Cluster test cases from similarity matrix.",
                default_value=None,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="similarity_matrix_workbook",
                display_name="Similarity matrix (.xlsx from Agent 3)",
                data_type=DataType.FILE,
                description="Workbook with sheet similarity_matrix (tc_ids as index/columns).",
                required=True,
                sample="lens_tc_similarity_matrix.xlsx",
                default_value=None,
                source_priority=[DataSource.USER],
            ),
            SkillInputParameter(
                name="cluster_threshold",
                display_name="Merge threshold τ",
                data_type=DataType.NUMBER,
                description="Union TC_i and TC_j when sim(i,j) > τ (strict).",
                required=False,
                sample=0.8,
                default_value=0.8,
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
            SkillOutputParameter(
                name="flow_graph_html_chained",
                data_type=DataType.FILE,
                description="Optional: HTML from Agent 2 when lens_chain_agent2 is enabled.",
                required=False,
                sample="lens_flow_graph.html",
            ),
            SkillOutputParameter(
                name="similarity_matrix_xlsx_chained",
                data_type=DataType.FILE,
                description="Optional: similarity workbook when chained Agent 2→3 succeeds.",
                required=False,
                sample="lens_tc_similarity_matrix.xlsx",
            ),
            SkillOutputParameter(
                name="clusters_xlsx_chained",
                data_type=DataType.FILE,
                description="Optional: Agent 4 clusters when chained Agent 3→4 succeeds.",
                required=False,
                sample="lens_tc_clusters.xlsx",
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
            SkillOutputParameter(
                name="similarity_matrix_xlsx",
                data_type=DataType.FILE,
                description="Present when lens_chain_agent3 is enabled: n×n cosine matrix from chained Agent 3.",
                required=False,
                sample="lens_tc_similarity_matrix.xlsx",
            ),
            SkillOutputParameter(
                name="clusters_xlsx",
                data_type=DataType.FILE,
                description="Present when lens_chain_agent4 is enabled: cluster assignments from chained Agent 4.",
                required=False,
                sample="lens_tc_clusters.xlsx",
            ),
        ]
    ),
    "lens_tc_similarity_skill": SkillOutputEnrichment(
        outputs=[
            SkillOutputParameter(
                name="summary",
                data_type=DataType.STRING,
                description="Markdown summary: n, pair count above threshold, method.",
                required=True,
                sample="n=12; 5 pairs ≥ 0.8.",
            ),
            SkillOutputParameter(
                name="similarity_matrix_xlsx",
                data_type=DataType.FILE,
                description="Excel: sheet similarity_matrix (n×n), sheet pairs_ge_threshold.",
                required=True,
                sample="lens_tc_similarity_matrix.xlsx",
            ),
            SkillOutputParameter(
                name="clusters_xlsx",
                data_type=DataType.FILE,
                description="Optional: Agent 4 output when lens_chain_agent4 is enabled.",
                required=False,
                sample="lens_tc_clusters.xlsx",
            ),
        ]
    ),
    "lens_tc_cluster_skill": SkillOutputEnrichment(
        outputs=[
            SkillOutputParameter(
                name="summary",
                data_type=DataType.STRING,
                description="Markdown: n, K clusters, effectiveness snapshot.",
                required=True,
                sample="n=10 → 4 clusters (sim > 0.8).",
            ),
            SkillOutputParameter(
                name="clusters_xlsx",
                data_type=DataType.FILE,
                description="cluster_assignments + cluster_summary sheets.",
                required=True,
                sample="lens_tc_clusters.xlsx",
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
            "**Agent 3 (similarity):** No LLM JSON — server builds TF–IDF vectors per test case from state chains "
            "and returns cosine-similarity matrix (diagonal 1).\n"
            "**Agent 4 (cluster):** No LLM — server unions TC pairs with sim(i,j) > τ (disjoint sets); outputs cluster assignments.\n"
        ),
        "skill_input_enrichments": skill_input_enrichments,
        "skill_output_enrichments": skill_output_enrichments,
    }
)
