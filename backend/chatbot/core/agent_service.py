"""Agent-team builder that reuses previously built Agent objects."""

from __future__ import annotations
from typing import List, Dict, Any, Optional, Union

import logging
import uuid
from typing import Dict, List, Set

from agents import Agent
from chatbot.models.agent_configuration import AgentConfiguration
from portal.models import Tenant

logger = logging.getLogger(__name__)

tool_registry = {}


def register_tool(name, func):
    """
    Registers a tool function with the given name.

    Args:
        name (str): Unique name of the tool.
        func (callable): The function to register.
    """
    tool_registry[name] = func


class AgentService:
    def create_agent(self, agent_model: AgentConfiguration) -> Agent:
        """
        Creates an Agent instance from a model, including tools and handoffs.

        Args:
            agent_model (AgentModel): The database model instance.

        Returns:
            Agent: An instance of the OpenAI Agents SDK Agent.
        """
        # Map tools to registered functions
        tools = [
            tool_registry[tool.name]
            for tool in agent_model.tools.all()
            if tool.name in tool_registry
        ]

        # Recursively create handoff agents
        handoffs = [
            self.create_agent(handoff)
            for handoff in agent_model.handoffs.all()
            if handoff.can_be_used_in_handoffs
        ]

        # tools = [
        #
        # ]
        # Instantiate the agent
        return Agent(
            name=agent_model.name,
            instructions=agent_model.instructions,
            model=agent_model.model,
            tools=tools,
            handoffs=handoffs,
        )


# =============================================================================
def get_handoff_list(root):
    """
    Depth-first search.
    Returns a flat list of AgentConfiguration objects reachable
    from `root`, excluding `root` itself and without duplicates.
    """
    visited = {root.pk}
    stack   = [root]
    result  = [root]

    while stack:
        node = stack.pop()
        # prefetch so we don't hit the DB inside the loop
        children = list(
            node.handoffs.exclude(pk=node.pk)    # paranoia: no self
                .prefetch_related("handoffs")     # 1 query per depth level
        )
        for child in children:
            if child.pk not in visited:
                visited.add(child.pk)
                result.append(child)
                stack.append(child)
    return result


class AgentTeam:

    def __init__(self, agent_id: str) -> None:

        self.team = []
        try:

            config = AgentConfiguration.objects.get(id=uuid.UUID(agent_id))
            # print(f"Target Agents to Load {get_handoff_list(config)}")

            for t in get_handoff_list(config):

                for h in t.handoffs.all():
                    print(h.name, h.id)

                tools_list = []
                # for tool in config.tools.all():
                #    tools_list.append(tool.name)

                handoffs_list = []
                for handoff in t.handoffs.all():
                    handoffs_list.append(handoff.name)

                a = Agent(
                    name=t.name,
                    instructions=t.instructions,
                    model=t.model,
                    tools=tools_list,
                    handoffs=handoffs_list
                )

                new_agent = {
                    "name": a.name,
                    "id": config.id,
                    "instance": a
                }
                print(new_agent)

                self.team.append(new_agent)

        except AgentConfiguration.DoesNotExist:

            logger.error(f'Agent {id} does not exist')

    @property
    def get_team(self):
        return self.team

    def get_agent(self, name: Optional[str] = None, agent_id: Optional[Union[str, int]] = None, _cache: Dict[tuple, Any] | None = None,):

        # parameter sanity ---------------------------------------------------
        if (name is None) == (agent_id is None):  # xor test
            raise ValueError("Specify *either* name or agent_id, not both / neither")

        key = ("name", name) if name is not None else ("id", str(agent_id))

        # fast path: use (optional) per-process cache ------------------------
        if _cache is not None and key in _cache:
            return _cache[key]

        # linear search ------------------------------------------------------
        for agent in self.team:
            if key[0] == "name" and agent["name"] == key[1]:
                result = agent["instance"]
                break
            if key[0] == "id" and str(agent["id"]) == key[1]:
                result = agent["instance"]
                break
        else:
            raise ValueError(f"No agent found for {key[0]}={key[1]!r}")

        # populate cache and return -----------------------------------------
        if _cache is not None:
            _cache[key] = result
        return result
