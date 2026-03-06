"""
Campaign Flow V2 - FSM-based campaign creation and lifecycle management.

This module provides a clean state machine implementation for campaign workflows,
supporting different channel/kind combinations with proper validation gates.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

from django.db import transaction
from django.utils import timezone
from viewflow import fsm

logger = logging.getLogger(__name__)


class CampaignStep(str, Enum):
    """Campaign configuration steps."""
    DRAFT = "draft"
    SELECT_TEMPLATE = "select_template"
    IMPORT_DATA = "import_data"
    CONFIGURE_MAPPING = "configure_mapping"
    SET_AUDIENCE = "set_audience"
    READY = "ready"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    ENDED = "ended"
    ARCHIVED = "archived"


class EndReason(str, Enum):
    """Reasons for campaign ending."""
    SUCCESS = "success"
    CANCELLED = "cancelled"
    ERROR = "error"
    EXPIRED = "expired"
    PARTIAL = "partial"


@dataclass
class StepRequirements:
    """Requirements configuration for a campaign kind/channel combination."""
    steps: List[str] = field(default_factory=list)
    optional_steps: List[str] = field(default_factory=list)
    required_for_ready: List[str] = field(default_factory=list)
    schedule_required: bool = False


CAMPAIGN_REQUIREMENTS: Dict[Tuple[str, str], StepRequirements] = {
    ("whatsapp", "express"): StepRequirements(
        steps=["select_template", "import_data", "configure_mapping", "set_audience"],
        optional_steps=["schedule"],
        required_for_ready=["has_template", "has_data", "has_mapping", "has_audience"],
        schedule_required=False,
    ),
    ("whatsapp", "one_shot"): StepRequirements(
        steps=["select_template", "set_audience"],
        optional_steps=["schedule"],
        required_for_ready=["has_template", "has_audience"],
        schedule_required=False,
    ),
    ("whatsapp", "drip"): StepRequirements(
        steps=["select_template", "set_audience", "configure_flow"],
        optional_steps=[],
        required_for_ready=["has_template", "has_audience", "has_flow"],
        schedule_required=True,
    ),
    ("whatsapp", "planned"): StepRequirements(
        steps=["select_template", "set_audience"],
        optional_steps=[],
        required_for_ready=["has_template", "has_audience", "has_schedule"],
        schedule_required=True,
    ),
    ("email", "express"): StepRequirements(
        steps=["select_template", "import_data", "configure_mapping", "set_audience"],
        optional_steps=["schedule"],
        required_for_ready=["has_template", "has_data", "has_mapping", "has_audience"],
        schedule_required=False,
    ),
    ("email", "one_shot"): StepRequirements(
        steps=["select_template", "set_audience"],
        optional_steps=["schedule"],
        required_for_ready=["has_template", "has_audience"],
        schedule_required=False,
    ),
    ("sms", "express"): StepRequirements(
        steps=["select_template", "import_data", "configure_mapping", "set_audience"],
        optional_steps=["schedule"],
        required_for_ready=["has_template", "has_data", "has_mapping", "has_audience"],
        schedule_required=False,
    ),
    ("sms", "one_shot"): StepRequirements(
        steps=["select_template", "set_audience"],
        optional_steps=["schedule"],
        required_for_ready=["has_template", "has_audience"],
        schedule_required=False,
    ),
    ("telegram", "express"): StepRequirements(
        steps=["select_template", "import_data", "configure_mapping", "set_audience"],
        optional_steps=["schedule"],
        required_for_ready=["has_template", "has_data", "has_mapping", "has_audience"],
        schedule_required=False,
    ),
    ("telegram", "one_shot"): StepRequirements(
        steps=["select_template", "set_audience"],
        optional_steps=["schedule"],
        required_for_ready=["has_template", "has_audience"],
        schedule_required=False,
    ),
}

DEFAULT_REQUIREMENTS = StepRequirements(
    steps=["select_template", "set_audience"],
    optional_steps=["schedule"],
    required_for_ready=["has_template", "has_audience"],
    schedule_required=False,
)


def get_campaign_requirements(channel: str, kind: str) -> StepRequirements:
    """Get the requirements for a specific channel/kind combination."""
    key = (channel.lower(), kind.lower())
    return CAMPAIGN_REQUIREMENTS.get(key, DEFAULT_REQUIREMENTS)


@dataclass
class ConfigurationState:
    """Current configuration state of a campaign."""
    has_template: bool = False
    has_data: bool = False
    has_mapping: bool = False
    has_audience: bool = False
    has_schedule: bool = False
    has_flow: bool = False
    template_id: Optional[str] = None
    data_staging_id: Optional[str] = None
    audience_id: Optional[str] = None
    audience_size: int = 0
    schedule_date: Optional[str] = None
    mapping_complete: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_template": self.has_template,
            "has_data": self.has_data,
            "has_mapping": self.has_mapping,
            "has_audience": self.has_audience,
            "has_schedule": self.has_schedule,
            "has_flow": self.has_flow,
            "template_id": self.template_id,
            "data_staging_id": self.data_staging_id,
            "audience_id": self.audience_id,
            "audience_size": self.audience_size,
            "schedule_date": self.schedule_date,
            "mapping_complete": self.mapping_complete,
        }
    
    @classmethod
    def from_campaign(cls, campaign) -> "ConfigurationState":
        """Build configuration state from a Campaign instance."""
        config = campaign.config or {}
        message_config = config.get("message", {})
        data_config = config.get("data", {})
        schedule_config = config.get("schedule", {})
        
        has_template = bool(message_config.get("whatsapp_template_id") or message_config.get("email_template_id"))
        has_data = bool(data_config.get("data_staging"))
        has_mapping = bool(message_config.get("map")) and message_config.get("mapping_complete", False)
        has_audience = campaign.audience_id is not None and (campaign.audience.size if campaign.audience else 0) > 0
        has_schedule = bool(schedule_config.get("date"))
        has_flow = bool(config.get("flow", {}).get("definition"))
        
        return cls(
            has_template=has_template,
            has_data=has_data,
            has_mapping=has_mapping,
            has_audience=has_audience,
            has_schedule=has_schedule,
            has_flow=has_flow,
            template_id=message_config.get("whatsapp_template_id") or message_config.get("email_template_id"),
            data_staging_id=data_config.get("data_staging"),
            audience_id=str(campaign.audience_id) if campaign.audience_id else None,
            audience_size=campaign.audience.size if campaign.audience else 0,
            schedule_date=schedule_config.get("date"),
            mapping_complete=message_config.get("mapping_complete", False),
        )


class CampaignFlowV2:
    """
    FSM-based campaign flow controller.
    
    Manages campaign lifecycle transitions with proper validation gates
    for each step based on channel and kind requirements.
    """
    
    step = fsm.State(CampaignStep, default=CampaignStep.DRAFT)
    
    def __init__(self, campaign):
        self.campaign = campaign
        self._requirements = get_campaign_requirements(campaign.channel, campaign.kind)
        self._config_state = ConfigurationState.from_campaign(campaign)
    
    @step.setter()
    def _set_step(self, value: CampaignStep):
        step_to_status = {
            CampaignStep.DRAFT: "draft",
            CampaignStep.SELECT_TEMPLATE: "draft",
            CampaignStep.IMPORT_DATA: "draft",
            CampaignStep.CONFIGURE_MAPPING: "draft",
            CampaignStep.SET_AUDIENCE: "draft",
            CampaignStep.READY: "ready",
            CampaignStep.SCHEDULED: "scheduled",
            CampaignStep.ACTIVE: "active",
            CampaignStep.ENDED: "ended",
            CampaignStep.ARCHIVED: "archived",
        }
        self.campaign.status = step_to_status.get(value, "draft")
        
        config = self.campaign.config or {}
        config["current_step"] = value.value
        self.campaign.config = config
    
    @step.getter()
    def _get_step(self) -> CampaignStep:
        config = self.campaign.config or {}
        current = config.get("current_step", "draft")
        try:
            return CampaignStep(current)
        except ValueError:
            return CampaignStep.DRAFT
    
    def get_configuration_state(self) -> ConfigurationState:
        """Get the current configuration state."""
        return ConfigurationState.from_campaign(self.campaign)
    
    def get_requirements(self) -> StepRequirements:
        """Get requirements for this campaign's channel/kind."""
        return self._requirements
    
    def get_missing_requirements(self) -> List[str]:
        """Get list of requirements not yet satisfied."""
        state = self.get_configuration_state()
        missing = []
        for req in self._requirements.required_for_ready:
            if not getattr(state, req, False):
                missing.append(req)
        return missing
    
    def get_allowed_actions(self) -> List[str]:
        """Get list of actions available from current state."""
        current = self._get_step()
        state = self.get_configuration_state()
        actions = []
        
        config_steps = {
            CampaignStep.DRAFT,
            CampaignStep.SELECT_TEMPLATE,
            CampaignStep.IMPORT_DATA,
            CampaignStep.CONFIGURE_MAPPING,
            CampaignStep.SET_AUDIENCE,
        }
        
        if current in config_steps:
            if "select_template" in self._requirements.steps:
                actions.append("select_template")
            if "import_data" in self._requirements.steps:
                actions.append("import_data")
            if "configure_mapping" in self._requirements.steps and state.has_template and state.has_data:
                actions.append("configure_mapping")
            if "set_audience" in self._requirements.steps:
                actions.append("set_audience")
            if "schedule" in self._requirements.optional_steps or self._requirements.schedule_required:
                actions.append("set_schedule")
            
            if not self.get_missing_requirements():
                actions.append("mark_ready")
        
        if current == CampaignStep.READY:
            actions.extend(["launch_now", "set_schedule", "rollback"])
            if state.has_schedule:
                actions.append("schedule_launch")
        
        if current == CampaignStep.SCHEDULED:
            actions.extend(["cancel_schedule", "launch_now", "rollback"])
        
        if current == CampaignStep.ACTIVE:
            actions.extend(["pause", "cancel", "complete"])
        
        if current == CampaignStep.ENDED:
            actions.append("archive")
        
        return actions
    
    def _validate_can_transition(self, target: CampaignStep) -> Tuple[bool, Optional[str]]:
        """Validate if transition to target state is allowed."""
        current = self._get_step()
        state = self.get_configuration_state()
        
        if target == CampaignStep.READY:
            missing = self.get_missing_requirements()
            if missing:
                return False, f"Missing requirements: {', '.join(missing)}"
        
        if target == CampaignStep.SCHEDULED:
            if not state.has_schedule:
                return False, "Schedule date is required"
        
        if target == CampaignStep.ACTIVE:
            if current not in (CampaignStep.READY, CampaignStep.SCHEDULED):
                return False, "Campaign must be in READY or SCHEDULED state to launch"
            if not state.has_audience or state.audience_size == 0:
                return False, "Campaign must have an audience with members"
        
        return True, None
    
    @step.transition(
        source=[CampaignStep.DRAFT, CampaignStep.SELECT_TEMPLATE, CampaignStep.IMPORT_DATA, 
                CampaignStep.CONFIGURE_MAPPING, CampaignStep.SET_AUDIENCE],
        target=CampaignStep.SELECT_TEMPLATE
    )
    def select_template(self, template_id: str, template_requirements: Optional[Any] = None):
        """Select a message template for the campaign."""
        config = self.campaign.config or {}
        message = config.get("message", {})
        
        if self.campaign.channel == "whatsapp":
            message["whatsapp_template_id"] = template_id
        elif self.campaign.channel == "email":
            message["email_template_id"] = template_id
        else:
            message["template_id"] = template_id
        
        if template_requirements:
            message["template_requirements"] = template_requirements
        
        message["mapping_complete"] = False
        config["message"] = message
        self.campaign.config = config
        logger.info(f"Campaign {self.campaign.pk}: Template {template_id} selected")
    
    @step.transition(
        source=[CampaignStep.DRAFT, CampaignStep.SELECT_TEMPLATE, CampaignStep.IMPORT_DATA,
                CampaignStep.CONFIGURE_MAPPING, CampaignStep.SET_AUDIENCE],
        target=CampaignStep.IMPORT_DATA
    )
    def import_data(self, staging_id: str, headers: List[str], row_count: int):
        """Import data for the campaign."""
        config = self.campaign.config or {}
        data = config.get("data", {})
        
        data["data_staging"] = staging_id
        data["headers"] = headers
        data["row_count"] = row_count
        data["imported_at"] = timezone.now().isoformat()
        
        config["data"] = data
        self.campaign.config = config
        logger.info(f"Campaign {self.campaign.pk}: Data imported ({row_count} rows)")
    
    @step.transition(
        source=[CampaignStep.SELECT_TEMPLATE, CampaignStep.IMPORT_DATA, 
                CampaignStep.CONFIGURE_MAPPING, CampaignStep.SET_AUDIENCE],
        target=CampaignStep.CONFIGURE_MAPPING
    )
    def configure_mapping(self, mapping: List[Dict], contact_name_field: Optional[str] = None):
        """Configure variable mapping between data and template."""
        state = self.get_configuration_state()
        if not state.has_template:
            raise ValueError("Template must be selected before configuring mapping")
        if not state.has_data and "import_data" in self._requirements.steps:
            raise ValueError("Data must be imported before configuring mapping")
        
        config = self.campaign.config or {}
        message = config.get("message", {})
        
        message["map"] = mapping
        message["contact_name_field"] = contact_name_field
        message["mapping_complete"] = True
        
        config["message"] = message
        self.campaign.config = config
        logger.info(f"Campaign {self.campaign.pk}: Mapping configured")
    
    @step.transition(
        source=[CampaignStep.DRAFT, CampaignStep.SELECT_TEMPLATE, CampaignStep.IMPORT_DATA,
                CampaignStep.CONFIGURE_MAPPING, CampaignStep.SET_AUDIENCE],
        target=CampaignStep.SET_AUDIENCE
    )
    def set_audience(self, audience):
        """Set the target audience for the campaign."""
        if audience.size == 0:
            raise ValueError("Audience must have at least one member")
        
        self.campaign.audience = audience
        logger.info(f"Campaign {self.campaign.pk}: Audience {audience.pk} set ({audience.size} members)")
    
    @step.transition(
        source=[CampaignStep.DRAFT, CampaignStep.SELECT_TEMPLATE, CampaignStep.IMPORT_DATA,
                CampaignStep.CONFIGURE_MAPPING, CampaignStep.SET_AUDIENCE],
        target=CampaignStep.READY
    )
    def mark_ready(self):
        """Mark campaign as ready for launch after validating all requirements."""
        can_transition, error = self._validate_can_transition(CampaignStep.READY)
        if not can_transition:
            raise ValueError(error)
        
        config = self.campaign.config or {}
        config["validated_at"] = timezone.now().isoformat()
        self.campaign.config = config
        logger.info(f"Campaign {self.campaign.pk}: Marked as ready")
    
    @step.transition(source=CampaignStep.READY, target=CampaignStep.READY)
    def set_schedule(self, schedule_date: str):
        """Set a schedule date for the campaign."""
        config = self.campaign.config or {}
        schedule = config.get("schedule", {})
        
        schedule["date"] = schedule_date
        schedule["scheduled_at"] = timezone.now().isoformat()
        
        config["schedule"] = schedule
        self.campaign.config = config
        logger.info(f"Campaign {self.campaign.pk}: Scheduled for {schedule_date}")
    
    @step.transition(source=CampaignStep.READY, target=CampaignStep.SCHEDULED)
    def schedule_launch(self):
        """Confirm schedule and move to SCHEDULED state."""
        state = self.get_configuration_state()
        if not state.has_schedule:
            raise ValueError("Schedule date must be set before scheduling")
        
        config = self.campaign.config or {}
        config["schedule"]["confirmed_at"] = timezone.now().isoformat()
        self.campaign.config = config
        logger.info(f"Campaign {self.campaign.pk}: Launch scheduled")
    
    @step.transition(
        source=[CampaignStep.READY, CampaignStep.SCHEDULED],
        target=CampaignStep.ACTIVE
    )
    def launch_now(self) -> str:
        """Launch the campaign immediately."""
        audience = self.campaign.audience
        if audience:
            audience_size = audience.size
            if audience_size == 0:
                raise ValueError("Audience has no members - cannot launch campaign")
        
        can_transition, error = self._validate_can_transition(CampaignStep.ACTIVE)
        if not can_transition:
            raise ValueError(error)
        
        config = self.campaign.config or {}
        config["launched_at"] = timezone.now().isoformat()
        config["schedule"] = {}
        self.campaign.config = config
        
        logger.info(f"Campaign {self.campaign.pk}: Launched")
        return "launched"
    
    @step.transition(source=CampaignStep.SCHEDULED, target=CampaignStep.READY)
    def cancel_schedule(self):
        """Cancel scheduled launch and return to READY state."""
        config = self.campaign.config or {}
        schedule = config.get("schedule", {})
        schedule.pop("confirmed_at", None)
        config["schedule"] = schedule
        config["current_step"] = CampaignStep.READY.value
        self.campaign.config = config
        self.campaign.status = "ready"
        logger.info(f"Campaign {self.campaign.pk}: Schedule cancelled")
    
    @step.transition(source=CampaignStep.ACTIVE, target=CampaignStep.ENDED)
    def complete(self, reason: EndReason = EndReason.SUCCESS):
        """Mark campaign as completed."""
        config = self.campaign.config or {}
        config["ended_at"] = timezone.now().isoformat()
        config["end_reason"] = reason.value
        self.campaign.config = config
        logger.info(f"Campaign {self.campaign.pk}: Completed with reason {reason.value}")
    
    @step.transition(source=CampaignStep.ACTIVE, target=CampaignStep.ENDED)
    def cancel(self):
        """Cancel an active campaign."""
        config = self.campaign.config or {}
        config["ended_at"] = timezone.now().isoformat()
        config["end_reason"] = EndReason.CANCELLED.value
        self.campaign.config = config
        logger.info(f"Campaign {self.campaign.pk}: Cancelled")
    
    @step.transition(
        source=[CampaignStep.READY, CampaignStep.SCHEDULED],
        target=CampaignStep.SET_AUDIENCE
    )
    def rollback(self):
        """Rollback to configuration state."""
        config = self.campaign.config or {}
        config.pop("validated_at", None)
        schedule = config.get("schedule", {})
        schedule.pop("confirmed_at", None)
        config["schedule"] = schedule
        config["current_step"] = CampaignStep.SET_AUDIENCE.value
        self.campaign.config = config
        self.campaign.status = "draft"
        logger.info(f"Campaign {self.campaign.pk}: Rolled back to configuration")
    
    @step.transition(source=CampaignStep.ENDED, target=CampaignStep.ARCHIVED)
    def archive(self):
        """Archive a completed campaign."""
        config = self.campaign.config or {}
        config["archived_at"] = timezone.now().isoformat()
        self.campaign.config = config
        logger.info(f"Campaign {self.campaign.pk}: Archived")
    
    @step.on_success()
    def _on_transition_success(self, descriptor, source, target):
        """Save campaign after successful transition."""
        self.campaign.save()


def get_campaign_flow(campaign) -> CampaignFlowV2:
    """Factory function to get a flow controller for a campaign."""
    return CampaignFlowV2(campaign)
