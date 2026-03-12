"""
Re-export Agent Console consumer from agent_console app (deprecated).
Use agent_console.consumers.agent_console instead.
"""
from agent_console.consumers.agent_console import AgentConsoleConsumer

__all__ = ["AgentConsoleConsumer"]
