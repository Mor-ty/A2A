"""Smoke tests and wiring checks for create_app() in __main__.py."""

import os
import importlib.util
from unittest.mock import MagicMock, patch


def _load_app_module():
    root = os.path.dirname(os.path.dirname(__file__))
    spec = importlib.util.spec_from_file_location("project_main", os.path.join(root, "__main__.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _patched_create_app():
    with patch("agentic_os_infra.core.config_store.config_store_class.SQLiteConfigStore"), \
         patch("agentic_os_infra.core.config_store.data_to_persist_store.SQLiteContextDataStore"), \
         patch("agentic_os_infra.executor.agent_executor.MyAgentExecutor") as mock_executor, \
         patch("a2a.server.request_handlers.default_request_handler.DefaultRequestHandler"), \
         patch("a2a.server.apps.jsonrpc.starlette_app.A2AStarletteApplication") as mock_server:

        fake_app = MagicMock()
        fake_app.routes = []
        mock_server.return_value.build.return_value = fake_app
        mod = _load_app_module()
        app = mod.create_app()

    return mock_executor, fake_app, app


class TestCreateApp:

    def test_create_app_returns_app(self):
        _, _, app = _patched_create_app()
        assert app is not None

    def test_extended_agent_card_route_registered(self):
        _, fake_app, _ = _patched_create_app()
        route_names = [r.name for r in fake_app.routes]
        assert "extended_agent_card" in route_names, \
            "/extended-agent-card route was not registered"

    def test_all_layer_classes_importable(self):
        from layers.agent_logic import AgentLogicLayer
        from layers.compliance import ComplianceLayer
        from layers.evaluation import EvaluationLayer
        from layers.guardrails import GuardrailsLayer
        from layers.configuration import ConfigurationLayer

        for cls in (AgentLogicLayer, ComplianceLayer, EvaluationLayer,
                    GuardrailsLayer, ConfigurationLayer):
            assert cls is not None


class TestLayerWiring:

    def test_logic_layer_is_agent_logic_layer(self):
        from layers.agent_logic import AgentLogicLayer
        mock_executor, _, _ = _patched_create_app()
        _, kwargs = mock_executor.call_args
        assert kwargs["logic_layer"] is AgentLogicLayer

    def test_compliance_layer_is_correct(self):
        from layers.compliance import ComplianceLayer
        mock_executor, _, _ = _patched_create_app()
        _, kwargs = mock_executor.call_args
        assert kwargs["compliance_layer"] is ComplianceLayer

    def test_evaluation_layer_is_correct(self):
        from layers.evaluation import EvaluationLayer
        mock_executor, _, _ = _patched_create_app()
        _, kwargs = mock_executor.call_args
        assert kwargs["evaluation_layer"] is EvaluationLayer

    def test_guardrails_layer_is_correct(self):
        from layers.guardrails import GuardrailsLayer
        mock_executor, _, _ = _patched_create_app()
        _, kwargs = mock_executor.call_args
        assert kwargs["guardrails_layer"] is GuardrailsLayer

    def test_configuration_layer_is_correct(self):
        from layers.configuration import ConfigurationLayer
        mock_executor, _, _ = _patched_create_app()
        _, kwargs = mock_executor.call_args
        assert kwargs["configuration_layer"] is ConfigurationLayer

    def test_my_agent_executor_is_used(self):
        mock_executor, _, _ = _patched_create_app()
        assert mock_executor.called, "MyAgentExecutor was never instantiated"

    def test_extended_agent_card_passed_to_executor(self):
        from agent_card import extended_agent_card
        mock_executor, _, _ = _patched_create_app()
        _, kwargs = mock_executor.call_args
        assert kwargs["extended_agent_card"] is extended_agent_card
