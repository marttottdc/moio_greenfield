"""Resolvers: inject workspace, profiles, skills, plugins, integration status from Django into runtime."""

from agent_console.resolvers.django_resolvers import build_resolvers_for_backend

__all__ = ["build_resolvers_for_backend"]
