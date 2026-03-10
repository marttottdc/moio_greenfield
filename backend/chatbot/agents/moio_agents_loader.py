# services/agents.py
from __future__ import annotations
import inspect

from typing import Dict, Set, List

from chatbot.models.agent_configuration import AgentConfiguration
from central_hub.models import Tenant
from agents import Agent, ModelSettings

from agents.tool import FunctionTool, WebSearchTool, ComputerTool, FileSearchTool, CodeInterpreterTool
import moio_platform.lib.moio_agent_tools_repo


def get_available_tools():

    tools_list = [
        obj for name, obj in inspect.getmembers(moio_platform.lib.moio_agent_tools_repo)
        if isinstance(obj, FunctionTool)
    ]

    return tools_list


import inspect
from typing import List

EMBEDDED_TOOL_MAP = {
    "web_search": WebSearchTool,
    "computer": ComputerTool,
    "file_search": FileSearchTool,
    "code_interpreter": CodeInterpreterTool,
}

# CodeInterpreterTool requires tool_config (Responses API: container in "auto" mode).
_DEFAULT_CODE_INTERPRETER_CONFIG = {
    "type": "code_interpreter",
    "container": {"type": "auto", "memory_limit": "4g"},
}


def get_function_tools(module, cfg: AgentConfiguration):

    tools = cfg.tools or {}

    embedded_tools = []

    # ----------------------------
    # 1) MODO VIEJO: lista simple
    # ----------------------------
    if isinstance(tools, list):
        old_mode_tools = tools
        hosted_dict = {}
        agent_tools = []
    else:
        # ----------------------------
        # 2) MODO NUEVO: dict
        # ----------------------------
        old_mode_tools = []
        hosted_dict = tools.get("hosted") or {}
        agent_tools = tools.get("agent_tools") or []

    # ----------------------------
    # 3) Embebidas por hosted flags
    # ----------------------------
    for key, enabled in hosted_dict.items():
        if not enabled or key not in EMBEDDED_TOOL_MAP:
            continue
        if key == "code_interpreter":
            embedded_tools.append(CodeInterpreterTool(tool_config=_DEFAULT_CODE_INTERPRETER_CONFIG))
        else:
            embedded_tools.append(EMBEDDED_TOOL_MAP[key]())

    # ----------------------------
    # 4) Normalizar lista final de nombres
    # ----------------------------
    tool_names = set(agent_tools + old_mode_tools)

    # ----------------------------
    # 5) Instancias dinámicas de FunctionTool
    # ----------------------------
    dynamic_tools = [
        obj
        for name, obj in inspect.getmembers(module)
        if isinstance(obj, FunctionTool) and name in tool_names
    ]

    # ----------------------------
    # 6) Apply tenant customizations (custom descriptions, default_params)
    # ----------------------------
    try:
        from chatbot.models.tenant_tool_configuration import TenantToolConfiguration
        tenant_configs = {
            tc.tool_name: tc 
            for tc in TenantToolConfiguration.objects.filter(tenant=cfg.tenant)
        }
        
        # Apply custom descriptions to dynamic tools if available
        for tool in dynamic_tools:
            if tool.name in tenant_configs:
                config = tenant_configs[tool.name]
                if config.custom_description:
                    tool.description = config.custom_description
    except Exception:
        # Fail silently on any DB errors
        pass

    # ----------------------------
    # Resultado final homogéneo
    # ----------------------------
    return embedded_tools + dynamic_tools



def build_agents_for_tenant(tenant: Tenant) -> Dict[str, Agent]:
    """
    Load all AgentConfiguration records reachable inside this tenant,
    create one Agent() for each unique *name*, and wire their hand-offs.

    Returns
    -------
    Dict[str, Agent]
        Mapping name → Agent instance (one per name, even if reused).
    """

    # ------------------------------------------------------------------ #
    # 1. Pull *all* configs once, keyed by name                           #
    # ------------------------------------------------------------------ #
    cfg_qs = (
        AgentConfiguration.objects.filter(tenant=tenant)
        .prefetch_related("handoffs")          # brings first-level links into RAM
    )
    by_name: Dict[str, AgentConfiguration] = {cfg.name: cfg for cfg in cfg_qs}

    # ------------------------------------------------------------------ #
    # 2. Discover every reachable name via BFS                            #
    # ------------------------------------------------------------------ #
    def bfs_names(start_cfgs: List[AgentConfiguration]) -> Set[str]:
        seen: Set[str] = set()
        queue: List[AgentConfiguration] = list(start_cfgs)
        while queue:
            cfg = queue.pop(0)
            if cfg.name in seen:
                continue
            seen.add(cfg.name)
            # enqueue children (hand-offs)
            queue.extend(cfg.handoffs.all())
        return seen

    required_names = bfs_names(list(by_name.values()))

    # ------------------------------------------------------------------ #
    # 3. Verify no missing configs                                        #
    # ------------------------------------------------------------------ #
    missing = required_names - by_name.keys()
    if missing:
        # One extra DB round-trip for any stray names referenced only
        # as hand-offs but not in the first query.
        extra_qs = (
            AgentConfiguration.objects.filter(tenant=tenant, name__in=missing)
            .prefetch_related("handoffs")
        )
        for cfg in extra_qs:
            by_name[cfg.name] = cfg
        still_missing = missing - by_name.keys()
        if still_missing:
            raise ValueError(f"Config(s) not found for: {', '.join(still_missing)}")

    # ------------------------------------------------------------------ #
    # 4. Instantiate each Agent exactly once                              #
    # ------------------------------------------------------------------ #
    id_to_agent: Dict[str, Agent] = {}
    for cfg in by_name.values():

        settings_instance = cfg.model_settings
        model_settings = ModelSettings(**settings_instance)

        agent = Agent(
            name=cfg.name,
            instructions=cfg.instructions or "",
            model=str(cfg.model),
            model_settings=model_settings,
            tools=get_function_tools(moio_platform.lib.moio_agent_tools_repo, cfg),
        )
        id_to_agent[cfg.name] = agent

    # ------------------------------------------------------------------ #
    # 5. Wire hand-offs (shared instances)                                #
    # ------------------------------------------------------------------ #
    for cfg in by_name.values():
        agent = id_to_agent[cfg.name]
        agent.handoffs = [
            id_to_agent[h.name]                   # same Python object reused
            for h in cfg.handoffs.all()
            if h.name in id_to_agent              # defensive
        ]

    return id_to_agent


# Example usage:
# tools = get_function_tools(moio_platform.lib.moio_agent_tools_repo)

# for tool in tools:
#    print("--------------")
#    print(f"Tool Name: {tool.name}")
#    print(f"Description: {tool.description}")
