"""Contract tests for agent_card.py."""

from agent_card import extended_agent_card, public_agent_card, skill_input_enrichments, skill_output_enrichments
from agentic_os_infra.core.extended_agent_card import ExtendedAgentCard
from a2a.types import AgentCard



class TestExtendedAgentCardExport:
    def test_extended_agent_card_exported(self):
        assert extended_agent_card is not None

    def test_extended_agent_card_is_correct_type(self):
        assert isinstance(extended_agent_card, ExtendedAgentCard), \
            "extended_agent_card must be an ExtendedAgentCard instance"

    def test_public_agent_card_exported(self):
        assert public_agent_card is not None

    def test_public_agent_card_is_agentcard(self):
        assert isinstance(public_agent_card, AgentCard)



class TestAgentCardMandatoryFields:
    def test_name_present(self):
        assert extended_agent_card.name, "AgentCard.name must not be empty"

    def test_description_present(self):
        assert extended_agent_card.description, "AgentCard.description must not be empty"

    def test_url_present(self):
        assert extended_agent_card.url, "AgentCard.url must not be empty"

    def test_version_present(self):
        assert extended_agent_card.version, "AgentCard.version must not be empty"

    def test_protocol_version_present(self):
        assert extended_agent_card.protocol_version, "protocol_version must not be empty"

    def test_capabilities_present(self):
        assert extended_agent_card.capabilities is not None

    def test_streaming_capability(self):
        assert extended_agent_card.capabilities.streaming is True



class TestAgentCardSkills:
    def test_at_least_one_skill(self):
        assert extended_agent_card.skills, "At least one AgentSkill must be defined"

    def test_all_skills_have_id(self):
        for skill in extended_agent_card.skills:
            assert skill.id, f"Skill is missing an id: {skill}"

    def test_all_skills_have_name(self):
        for skill in extended_agent_card.skills:
            assert skill.name, f"Skill '{skill.id}' is missing a name"

    def test_all_skills_have_description(self):
        for skill in extended_agent_card.skills:
            assert skill.description, f"Skill '{skill.id}' is missing a description"

    def test_skill_ids_are_unique(self):
        ids = [s.id for s in extended_agent_card.skills]
        assert len(ids) == len(set(ids)), "Duplicate skill IDs detected"



# this is not a MUST but if exist in the agent card only then test it
class TestSkillEnrichments:
    def test_input_enrichments_exported(self):
        assert skill_input_enrichments is not None
        assert isinstance(skill_input_enrichments, dict)

    def test_output_enrichments_exported(self):
        assert skill_output_enrichments is not None
        assert isinstance(skill_output_enrichments, dict)

    def test_every_skill_has_input_enrichment(self):
        for skill in extended_agent_card.skills:
            assert skill.id in skill_input_enrichments, \
                f"No input enrichment defined for skill '{skill.id}'"

    def test_every_skill_has_output_enrichment(self):
        for skill in extended_agent_card.skills:
            assert skill.id in skill_output_enrichments, \
                f"No output enrichment defined for skill '{skill.id}'"

    def test_input_enrichments_have_at_least_one_parameter(self):
        for skill_id, enrichment in skill_input_enrichments.items():
            assert enrichment.parameters, \
                f"Skill '{skill_id}' input enrichment has no parameters"

    def test_output_enrichments_have_at_least_one_output(self):
        for skill_id, enrichment in skill_output_enrichments.items():
            assert enrichment.outputs, \
                f"Skill '{skill_id}' output enrichment has no outputs defined"



class TestExtendedFields:
    def test_required_blueprint_keys_is_list(self):
        assert isinstance(extended_agent_card.required_blueprint_keys, list)

    def test_system_prompt_exists(self):
        assert hasattr(extended_agent_card, "system_prompt")
        assert extended_agent_card.system_prompt is not None

    def test_active_flag_is_bool(self):
        assert isinstance(extended_agent_card.active, bool)

    def test_agentic_os_infra_flag_is_true(self):
        assert extended_agent_card.agentic_os_infra is True

    def test_id_is_set(self):
        assert extended_agent_card.id, "extended_agent_card.id must be set"


PLACEHOLDER_PATTERNS = ["TODO", "todo", "placeholder", "lorem ipsum", "test123", "my_agent"]


class TestNoPlaceholders:

    def _assert_no_placeholder(self, value: str, context: str):
        for pat in PLACEHOLDER_PATTERNS:
            assert pat not in value, f"{context} contains placeholder text '{pat}': {value!r}"

    def test_agent_name_is_not_placeholder(self):
        self._assert_no_placeholder(extended_agent_card.name, "Agent name")

    def test_agent_description_is_not_placeholder(self):
        self._assert_no_placeholder(extended_agent_card.description, "Agent description")

    def test_system_prompt_is_not_placeholder(self):
        prompt = extended_agent_card.system_prompt or ""
        self._assert_no_placeholder(prompt, "system_prompt")
        assert prompt.strip(), "system_prompt must not be empty"

    def test_skill_descriptions_are_not_placeholders(self):
        for skill in extended_agent_card.skills:
            self._assert_no_placeholder(skill.description, f"Skill '{skill.id}' description")

    def test_input_display_names_are_not_placeholders(self):
        for skill_id, enrichment in skill_input_enrichments.items():
            for p in enrichment.parameters:
                self._assert_no_placeholder(p.display_name, f"Skill '{skill_id}' input '{p.name}' display_name")

    def test_input_descriptions_are_not_placeholders(self):
        for skill_id, enrichment in skill_input_enrichments.items():
            for p in enrichment.parameters:
                if p.description:
                    self._assert_no_placeholder(p.description, f"Skill '{skill_id}' input '{p.name}' description")


