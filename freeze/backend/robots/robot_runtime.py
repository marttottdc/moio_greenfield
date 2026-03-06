from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any

from agents import Agent, ModelSettings, Runner, set_default_openai_key
from django.core.exceptions import ValidationError

import moio_platform.lib.moio_agent_tools_repo as tool_repo
from chatbot.agents.moio_agents_loader import get_function_tools
from chatbot.models.agent_configuration import AgentConfiguration
from portal.models import TenantConfiguration

from .contracts import validate_llm_output_contract
from .models import Robot, RobotRun, RobotSession

logger = logging.getLogger(__name__)
_OPENAI_KEY_LOCK = threading.Lock()


def _extract_messages_and_tool_calls(result: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    messages: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []

    new_items = getattr(result, "new_items", None)
    if not new_items:
        return messages, tool_calls

    for item in new_items:
        role = getattr(item, "role", None)
        content = getattr(item, "content", None)
        if role and content is not None:
            messages.append({"role": str(role), "content": content})

        tcs = getattr(item, "tool_calls", None)
        if tcs:
            for tc in tcs:
                tool_calls.append(
                    {
                        "name": getattr(tc, "name", "unknown"),
                        "args": getattr(tc, "arguments", {}),
                    }
                )

    return messages, tool_calls


def _normalise_conversation_history(transcript: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    allowed_roles = {"user", "assistant", "system", "developer"}
    for entry in transcript or []:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role") or "").strip().lower()
        content = entry.get("content")
        if role not in allowed_roles or content is None:
            continue
        if not isinstance(content, str):
            try:
                content = json.dumps(content, default=str)
            except TypeError:
                content = str(content)
        history.append({"role": role, "content": content})
    return history


def _apply_robot_tool_policy(tools: list[Any], tools_config: dict[str, Any]) -> list[Any]:
    allow = tools_config.get("allow") or []
    deny = tools_config.get("deny") or []
    allow_set = {str(x) for x in allow if x is not None and str(x).strip() != ""}
    deny_set = {str(x) for x in deny if x is not None and str(x).strip() != ""}

    if allow_set:
        return [t for t in tools if getattr(t, "name", None) in allow_set]
    if deny_set:
        return [t for t in tools if getattr(t, "name", None) not in deny_set]
    return tools


@dataclass(slots=True)
class RobotRuntime:
    robot: Robot
    agent_cfg: AgentConfiguration
    agent: Agent
    openai_api_key: str

    @classmethod
    def for_robot(cls, robot: Robot) -> "RobotRuntime":
        tenant_cfg = TenantConfiguration.objects.filter(tenant=robot.tenant).first()
        if not tenant_cfg or not tenant_cfg.openai_integration_enabled or not tenant_cfg.openai_api_key:
            raise RuntimeError("OpenAI integration is not configured for this tenant")

        agent_cfg_id = (robot.model_config or {}).get("agent_configuration_id")
        agent_cfg: AgentConfiguration | None = None
        if agent_cfg_id:
            agent_cfg = (
                AgentConfiguration.objects.filter(tenant=robot.tenant, id=agent_cfg_id).first()
            )
        if not agent_cfg:
            agent_cfg = AgentConfiguration.objects.filter(tenant=robot.tenant, default=True).first()
        if not agent_cfg:
            raise RuntimeError("No AgentConfiguration found for this tenant")

        tools = get_function_tools(tool_repo, agent_cfg)
        tools = _apply_robot_tool_policy(tools, robot.tools_config or {})

        contract = (
            "Return a single JSON object with keys: "
            "assistant_message (string), tool_calls (array), plan_patch (object|null), stop_reason (string). "
            "Return JSON only."
        )
        instructions = "\n\n".join(
            part for part in [agent_cfg.instructions or "", robot.system_prompt or "", contract] if part
        )

        model_settings_payload = agent_cfg.model_settings or {}
        model_settings = ModelSettings(**model_settings_payload) if model_settings_payload else None

        agent_kwargs: dict[str, Any] = {
            "name": agent_cfg.name or f"robot:{robot.slug}",
            "instructions": instructions,
            "model": str(agent_cfg.model),
            "tools": tools,
        }
        if model_settings is not None:
            agent_kwargs["model_settings"] = model_settings

        agent = Agent(**agent_kwargs)
        return cls(
            robot=robot,
            agent_cfg=agent_cfg,
            agent=agent,
            openai_api_key=tenant_cfg.openai_api_key,
        )

    def step(
        self,
        *,
        run: RobotRun,
        session: RobotSession,
        iteration: int,
        max_iterations: int,
        instruction_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """
        Returns: (llm_output_contract, extracted_tool_calls)
        """
        payload = run.trigger_payload or {}
        provided = payload.get("llm_output")
        if isinstance(provided, list):
            try:
                provided = provided[iteration - 1]
            except Exception:
                provided = None
        if isinstance(provided, dict):
            contract = validate_llm_output_contract(provided)
            extracted_tool_calls = contract.get("tool_calls") or []
            return contract, extracted_tool_calls

        conversation_history = _normalise_conversation_history(session.transcript)
        context = {
            "tenant_id": str(self.robot.tenant_id),
            "robot_id": str(self.robot.id),
            "run_id": str(run.id),
            "iteration": iteration,
            "max_iterations": max_iterations,
            "instruction": instruction_payload,
            "intent_state": session.intent_state or {},
            "bootstrap_context": self.robot.bootstrap_context or {},
            "targets": self.robot.targets or {},
        }

        # The Agents SDK key is process-global, so serialize key assignment and model calls.
        with _OPENAI_KEY_LOCK:
            set_default_openai_key(self.openai_api_key)
            result = asyncio.run(
                Runner.run(starting_agent=self.agent, input=conversation_history, context=context)
            )
        messages, extracted_tool_calls = _extract_messages_and_tool_calls(result)

        raw_output = getattr(result, "final_output", None)
        if raw_output in (None, "") and messages:
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and msg.get("content") not in (None, ""):
                    raw_output = msg.get("content")
                    break

        if isinstance(raw_output, str):
            try:
                raw_output = json.loads(raw_output.strip())
            except json.JSONDecodeError as exc:
                raise ValidationError(f"Robot agent output must be valid JSON: {exc}") from exc

        if not isinstance(raw_output, dict):
            raise ValidationError("Robot agent output must be a JSON object")

        # Ensure tool_calls comes from actual execution trace if model omitted it.
        if "tool_calls" not in raw_output:
            raw_output["tool_calls"] = extracted_tool_calls
        if not raw_output.get("tool_calls"):
            raw_output["tool_calls"] = extracted_tool_calls

        contract = validate_llm_output_contract(raw_output)
        return contract, extracted_tool_calls

