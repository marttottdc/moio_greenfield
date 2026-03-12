"""Agent Console Celery tasks: run automations via runtime."""

from agent_console.tasks.run_automation import run_agent_console_automation

__all__ = ["run_agent_console_automation"]
