"""Runtime utilities for executing agent-driven flows.

This module provides the concrete implementation for the agent handler used by
``FlowConnector``.  It bridges the declarative Flow configuration with the
existing chatbot agent infrastructure so we can reuse loaders, tools and
guardrails while still allowing per-flow overrides similar to the OpenAI
workflow builder example shared during planning.
"""

from dataclasses import dataclass, field, asdict, is_dataclass
import json
import logging
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

import inspect

from django.core.exceptions import ObjectDoesNotExist

from agents import Agent, ModelSettings, Runner, set_default_openai_key
from agents.tool import FunctionTool

try:  # guardrails are optional depending on the agents SDK version
    from agents.guardrails import InputGuardrail, OutputGuardrail
except ImportError:  # pragma: no cover - fallback for older SDKs
    InputGuardrail = OutputGuardrail = Any  # type: ignore

from central_hub.models import Tenant
from central_hub.tenant_config import get_tenant_config

import moio_platform.lib.moio_agent_tools_repo as tool_repo

from .branching import BranchWriter, BranchWriterConfig
from .lib import render_template_string

logger = logging.getLogger(__name__)


class FlowAgentExecutionError(RuntimeError):
    """Raised when the agent flow cannot be executed."""


def _normalise_output(value: Any) -> Any:
    """Return a JSON-compatible version of ``value`` when possible."""

    if value is None:
        return None

    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")  # pydantic v2 support
        except TypeError:
            return value.model_dump()

    if is_dataclass(value):
        return asdict(value)

    if isinstance(value, (bytes, bytearray)):
        return value.decode()

    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            try:
                return json.loads(trimmed)
            except json.JSONDecodeError:
                return value
        return value

    return value


def _extract_from_mapping(data: Mapping[str, Any], path: str) -> Any:
    """Extract value from nested ``data`` using dot-separated ``path``."""

    current: Any = data
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part not in current:
                raise FlowAgentExecutionError(
                    f"Missing key '{part}' while resolving path '{path}'")
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise FlowAgentExecutionError(
                    f"Expected list index while resolving path '{path}', got '{part}'"
                ) from exc
            try:
                current = current[index]
            except IndexError as exc:
                raise FlowAgentExecutionError(
                    f"Index {index} out of range while resolving path '{path}'"
                ) from exc
        else:
            raise FlowAgentExecutionError(
                f"Cannot descend into value of type {type(current)!r} for path '{path}'"
            )
    return current


# ---------------------------------------------------------------------------
#  Catalogues
# ---------------------------------------------------------------------------


class ToolCatalog:
    """Catalog of tools exposed to flow configurations."""

    def __init__(self) -> None:
        self._tools: Dict[str, FunctionTool] = {}
        for attr_name, obj in inspect.getmembers(tool_repo):
            if isinstance(obj, FunctionTool):
                self._tools.setdefault(attr_name, obj)
                self._tools.setdefault(obj.name, obj)

    def get(self, name: str) -> FunctionTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise FlowAgentExecutionError(
                f"Tool '{name}' is not registered") from exc

    def available(self) -> List[str]:
        return sorted(self._tools.keys())


class GuardrailCatalog:
    """Placeholder guardrail registry.

    Guardrails can be registered manually via ``register_input`` and
    ``register_output``.  This keeps the implementation flexible while still
    exposing a simple interface to flows.
    """

    def __init__(self) -> None:
        self._input: Dict[str, InputGuardrail] = {}
        self._output: Dict[str, OutputGuardrail] = {}

    def register_input(self, name: str, guardrail: InputGuardrail) -> None:
        self._input[name] = guardrail

    def register_output(self, name: str, guardrail: OutputGuardrail) -> None:
        self._output[name] = guardrail

    def get_input(self, name: str) -> InputGuardrail:
        try:
            return self._input[name]
        except KeyError as exc:
            raise FlowAgentExecutionError(
                f"Input guardrail '{name}' is not registered") from exc

    def get_output(self, name: str) -> OutputGuardrail:
        try:
            return self._output[name]
        except KeyError as exc:
            raise FlowAgentExecutionError(
                f"Output guardrail '{name}' is not registered") from exc


class OutputModelCatalog:
    """Simple catalog to map identifiers to output schema callables."""

    def __init__(self) -> None:
        self._models: Dict[str, Any] = {}

    def register(self, name: str, model: Any) -> None:
        self._models[name] = model

    def get(self, name: str) -> Any:
        try:
            return self._models[name]
        except KeyError as exc:
            raise FlowAgentExecutionError(
                f"Output model '{name}' is not registered") from exc


TOOL_CATALOG = ToolCatalog()
GUARDRAIL_CATALOG = GuardrailCatalog()
OUTPUT_MODEL_CATALOG = OutputModelCatalog()

# ---------------------------------------------------------------------------
#  Agent configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FlowAgentConfig:
    name: str
    tools: List[str] = field(default_factory=list)
    input_guardrails: List[str] = field(default_factory=list)
    output_guardrails: List[str] = field(default_factory=list)
    output_model: str | None = None
    instructions_override: str | None = None
    model_override: str | None = None
    model_settings: Dict[str, Any] = field(default_factory=dict)
    # New fields to match OpenAI workflow capabilities
    include_chat_history: bool = True
    reasoning_effort: str | None = None  # "low", "medium", "high" for reasoning models
    output_format: str = "text"  # "text", "json", or schema reference
    continue_on_error: bool = False
    write_to_conversation_history: bool = True
    # Input message with variable interpolation support
    input_message: str | None = None
    input_role: str = "user"  # "user" or "system"
    # Whether to reuse/persist session context within a flow execution.
    # (Handled at the flow executor level; included here so configs round-trip cleanly.)
    use_flow_session: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FlowAgentConfig":
        if "name" not in data:
            raise FlowAgentExecutionError(
                "Agent configuration must include 'name'")
        return cls(
            name=data["name"],
            tools=list(data.get("tools", [])),
            input_guardrails=list(data.get("input_guardrails", [])),
            output_guardrails=list(data.get("output_guardrails", [])),
            output_model=data.get("output_model"),
            instructions_override=data.get("instructions_override"),
            model_override=data.get("model_override"),
            model_settings=dict(data.get("model_settings", {})),
            include_chat_history=bool(data.get("include_chat_history", True)),
            reasoning_effort=data.get("reasoning_effort"),
            output_format=data.get("output_format", "text"),
            continue_on_error=bool(data.get("continue_on_error", False)),
            write_to_conversation_history=bool(
                data.get("write_to_conversation_history", True)),
            input_message=data.get("input_message"),
            input_role=data.get("input_role", "user"),
            use_flow_session=bool(data.get("use_flow_session", True)),
        )


@dataclass(slots=True)
class FlowClassifierConfig(FlowAgentConfig):
    output_field: str = "classification"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FlowClassifierConfig":
        cfg = super().from_dict(data)
        output_field = data.get("output_field", "classification")
        return cls(
            name=cfg.name,
            tools=cfg.tools,
            input_guardrails=cfg.input_guardrails,
            output_guardrails=cfg.output_guardrails,
            output_model=cfg.output_model,
            instructions_override=cfg.instructions_override,
            model_override=cfg.model_override,
            model_settings=cfg.model_settings,
            output_field=output_field,
        )

    def extract_value(self, payload: Any) -> Any:
        if isinstance(payload, Mapping):
            return payload.get(self.output_field)
        return payload


@dataclass(slots=True)
class FlowBranch:
    value: str
    agent: FlowAgentConfig
    approval_message: str | None = None
    require_approval: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FlowBranch":
        if "value" not in data:
            raise FlowAgentExecutionError("Branch definition requires 'value'")
        agent_cfg = FlowAgentConfig.from_dict(data.get("agent", {}))
        return cls(
            value=str(data["value"]),
            agent=agent_cfg,
            approval_message=data.get("approval_message"),
            require_approval=bool(data.get("require_approval", False)),
        )


@dataclass(slots=True)
class FlowAgentBlueprint:
    classifier: FlowClassifierConfig
    branches: Dict[str, FlowBranch]
    default_branch: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FlowAgentBlueprint":
        classifier = FlowClassifierConfig.from_dict(data.get("classifier", {}))
        branches_cfg = data.get("branches", [])
        if isinstance(branches_cfg, Mapping):
            branches_iterable = branches_cfg.values()
        else:
            branches_iterable = branches_cfg

        branches: Dict[str, FlowBranch] = {}
        for entry in branches_iterable:
            branch = FlowBranch.from_dict(entry)
            branches[branch.value] = branch

        if not branches:
            raise FlowAgentExecutionError(
                "Blueprint must define at least one branch")

        return cls(
            classifier=classifier,
            branches=branches,
            default_branch=data.get("default_branch"),
        )

    def resolve_branch(self, value: Any) -> FlowBranch:
        key = str(value)
        branch = self.branches.get(key)
        if branch:
            return branch
        if self.default_branch:
            fallback = self.branches.get(self.default_branch)
            if fallback:
                return fallback
        raise FlowAgentExecutionError(
            f"No branch found for classification '{value}'")


# ---------------------------------------------------------------------------
#  Agent execution runtime
# ---------------------------------------------------------------------------


class FlowAgentRuntime:
    """Builds and runs agents according to a blueprint."""

    def __init__(
        self,
        tenant: Tenant,
        tool_catalog: ToolCatalog | None = None,
        guardrail_catalog: GuardrailCatalog | None = None,
        output_catalog: OutputModelCatalog | None = None,
    ) -> None:
        self.tenant = tenant
        self._tool_catalog = tool_catalog or TOOL_CATALOG
        self._guardrail_catalog = guardrail_catalog or GUARDRAIL_CATALOG
        self._output_catalog = output_catalog or OUTPUT_MODEL_CATALOG

        # Set OpenAI API key before building agents
        tenant_cfg = get_tenant_config(tenant)
        if tenant_cfg and tenant_cfg.openai_api_key:
            logger.info("Setting default OpenAI API key for tenant %s", )
            set_default_openai_key(tenant_cfg.openai_api_key)

    def _build_agent(self, config: FlowAgentConfig):
        # Try to find existing agent in cache
        # base_agent = self._agent_cache.get(config.name) # Removed agent cache

        # If no base agent exists, create one from scratch
        # if base_agent is None: # Simplified logic since cache is removed
        # Create a new agent with flow configuration
        agent_kwargs: Dict[str, Any] = {
            "name": config.name,
            "instructions": config.instructions_override
            or "You are a helpful AI assistant.",
            "model": config.model_override or "gpt-4o",
        }

        if config.model_settings:
            agent_kwargs["model_settings"] = ModelSettings(
                **config.model_settings)

        if config.tools:
            agent_kwargs["tools"] = [
                self._tool_catalog.get(name) for name in config.tools
            ]

        if config.output_model:
            agent_kwargs["output_type"] = self._output_catalog.get(
                config.output_model)

        if config.input_guardrails:
            agent_kwargs["input_guardrails"] = [
                self._guardrail_catalog.get_input(name)
                for name in config.input_guardrails
            ]

        if config.output_guardrails:
            agent_kwargs["output_guardrails"] = [
                self._guardrail_catalog.get_output(name)
                for name in config.output_guardrails
            ]

        return Agent(**agent_kwargs)

        # Use existing agent as base and apply overrides
        # clone_kwargs: Dict[str, Any] = {}

        # if config.instructions_override is not None:
        #     clone_kwargs["instructions"] = config.instructions_override
        # if config.model_override is not None:
        #     clone_kwargs["model"] = config.model_override
        # if config.model_settings:
        #     override_settings = ModelSettings(**config.model_settings)
        #     clone_kwargs["model_settings"] = base_agent.model_settings.resolve(
        #         override_settings)
        # if config.tools:
        #     clone_kwargs["tools"] = [
        #         self._tool_catalog.get(name) for name in config.tools
        #     ]
        # if config.output_model:
        #     clone_kwargs["output_type"] = self._output_catalog.get(
        #         config.output_model)
        # if config.input_guardrails:
        #     clone_kwargs["input_guardrails"] = [
        #         self._guardrail_catalog.get_input(name)
        #         for name in config.input_guardrails
        #     ]
        # if config.output_guardrails:
        #     clone_kwargs["output_guardrails"] = [
        #         self._guardrail_catalog.get_output(name)
        #         for name in config.output_guardrails
        #     ]

        # if clone_kwargs:
        #     agent = base_agent.clone(**clone_kwargs)
        # else:
        #     agent = base_agent
        # return agent

    def _run_agent(self,
                   agent,
                   message: str,
                   context: Optional[Dict[str, Any]],
                   config: FlowAgentConfig | None = None):
        logger.info("Running agent '%s' for tenant %s", agent.name,
                    self.tenant)
        import asyncio

        # Get conversation history from context or initialize empty
        conversation_history = context.get("conversation_history",
                                           []) if context else []

        # Prepare the message with variable interpolation if configured
        final_message = message
        if config and config.input_message:
            # Render strict flow placeholders (same contract as email templates).
            # Only {{ctx.*}} placeholders should be used by the frontend composer.
            render_ctx: Dict[str, Any] = dict(context or {})
            # Expose the raw incoming message under a stable ctx path so templates can
            # reference it via {{ctx.workflow.input_as_text}}.
            workflow = render_ctx.get("workflow")
            if not isinstance(workflow, dict):
                workflow = {}
                render_ctx["workflow"] = workflow
            workflow.setdefault("input_as_text", message)
            workflow.setdefault("input", message)

            try:
                final_message = str(
                    render_template_string(
                        config.input_message,
                        payload={"message": message},
                        context=render_ctx,
                        autoescape_html=False,
                    )
                )
            except Exception as exc:
                raise FlowAgentExecutionError(
                    f"Failed to render agent input_message template: {exc}"
                ) from exc

        # Add the current message to history if configured
        if not config or config.include_chat_history:
            role = config.input_role if config else "user"
            conversation_history.append({
                "role": role,
                "content": final_message
            })

        # Update context with the new history
        if context:
            context["conversation_history"] = conversation_history

        # The OpenAI Agents SDK expects conversation history format.
        # Avoid logging full context/history (can be large or accidentally circular).
        try:
            logger.info("Conversation history size: %s",
                        len(conversation_history) if isinstance(conversation_history, list) else "n/a")
            logger.info("Context keys: %s",
                        sorted(list(context.keys())) if isinstance(context, dict) else "n/a")
        except Exception:
            pass

        return asyncio.run(
            Runner.run(starting_agent=agent,
                       input=conversation_history,
                       context=context))

    def _interpolate_variables(self, template: str, message: str,
                               context: Optional[Dict[str, Any]]) -> str:
        """Interpolate variables in template string like {{workflow.input_as_text}}"""
        import re

        # Create a data dict with available variables
        data = {"workflow": {"input_as_text": message, "input": message}}

        # Add context data if available
        if context:
            data.update(context)

        # Replace {{variable}} patterns
        def replace_var(match):
            var_path = match.group(1).strip()
            try:
                return str(_extract_from_mapping(data, var_path))
            except FlowAgentExecutionError:
                logger.warning(
                    f"Variable '{var_path}' not found in interpolation context"
                )
                return match.group(0)

        return re.sub(r'\{\{([^}]+)\}\}', replace_var, template)

    def run_blueprint(
        self,
        blueprint: FlowAgentBlueprint,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        branch_config: BranchWriterConfig | None = None,
    ) -> Dict[str, Any]:
        classifier_agent = self._build_agent(blueprint.classifier)
        classification_result = self._run_agent(classifier_agent, message,
                                                context, blueprint.classifier)
        classification_payload = _normalise_output(
            getattr(classification_result, "final_output",
                    classification_result))
        classification_value = blueprint.classifier.extract_value(
            classification_payload)

        branch = blueprint.resolve_branch(classification_value)

        branch_agent = self._build_agent(branch.agent)
        branch_result = self._run_agent(branch_agent, message, context,
                                        branch.agent)
        branch_payload = _normalise_output(
            getattr(branch_result, "final_output", branch_result))

        branch_execution: Dict[str, Any] | None = None
        if branch_config and isinstance(branch_payload, Mapping):
            branch_writer = BranchWriter(branch_config)
            branch_execution = branch_writer.apply_plan(branch_payload)

        return {
            "classification": classification_value,
            "classification_output": classification_payload,
            "branch": branch.value,
            "branch_output": branch_payload,
            "branch_execution": branch_execution,
        }


# ---------------------------------------------------------------------------
#  Executor entry-point used by FlowConnector
# ---------------------------------------------------------------------------


class AgentFlowExecutor:
    """Adapter invoked from ``FlowConnector``."""

    def execute(
        self,
        parameters: MutableMapping[str, Any],
        *,
        flow_id: str,
        trigger_args: Iterable[Any],
        trigger_kwargs: MutableMapping[str, Any],
    ) -> Dict[str, Any]:
        tenant_id = parameters.get("tenant_id")
        if not tenant_id:
            raise FlowAgentExecutionError(
                "Agent handler requires 'tenant_id' in parameters")

        try:
            tenant = Tenant.objects.get(id=tenant_id)

        except ObjectDoesNotExist as exc:
            raise FlowAgentExecutionError(
                f"Tenant '{tenant_id}' not found for agent handler") from exc

        webhook_payload = trigger_kwargs.get("webhook_payload")
        message_path = parameters.get("input_path", "webhook_payload.message")
        combined_payload = {"webhook_payload": webhook_payload}
        message = _extract_from_mapping(combined_payload, message_path)
        if not isinstance(message, str):
            raise FlowAgentExecutionError(
                "Resolved input message must be a string")

        blueprint_data = parameters.get("blueprint") or {}
        blueprint = FlowAgentBlueprint.from_dict(blueprint_data)

        branch_cfg = parameters.get("branch")
        branch_config = BranchWriterConfig(
            **branch_cfg) if branch_cfg else None

        runtime = FlowAgentRuntime(tenant)
        context = {
            "flow_id": flow_id,
            "tenant_id": str(tenant_id),
            "webhook_payload": webhook_payload,
            "trigger_args": list(trigger_args),
        }

        result = runtime.run_blueprint(
            blueprint,
            message,
            context=context,
            branch_config=branch_config,
        )

        logger.info(
            "Completed agent handler for flow %s with branch %s",
            flow_id,
            result.get("branch"),
        )
        return result


__all__ = [
    "AgentFlowExecutor",
    "FlowAgentBlueprint",
    "FlowAgentConfig",
    "FlowAgentExecutionError",
    "FlowAgentRuntime",
]
