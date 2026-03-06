"""
CRM rules and automation hooks.

Flow-trigger wiring: Use Flows with trigger_signal (e.g. on crm.Contact, crm.Deal)
or webhook triggers, and a CRM CRUD node with resource_slug "activity" or
"activity_suggestion" to create activities/suggestions from CRM events.
"""

from crm.rules.activity_rules import create_activity_suggestion_from_rule

__all__ = ["create_activity_suggestion_from_rule"]
