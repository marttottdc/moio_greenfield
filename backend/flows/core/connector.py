
from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import importlib
import logging
from collections import defaultdict

from django.utils.module_loading import import_string

from central_hub.event_bus import event_bus
from central_hub.webhooks.utils import get_handler
from central_hub.events import EventTypes

from .agent_runtime import AgentFlowExecutor, FlowAgentExecutionError


logger = logging.getLogger(__name__)


class TriggerType(Enum):
    WEBHOOK = "webhook"
    SCHEDULED = "scheduled" 
    EVENT = "event"
    MANUAL = "manual"


class HandlerType(Enum):
    TASK = "task"
    SHARED_TASK = "shared_task"
    AGENT = "agent"
    FUNCTION = "function"
    WEBHOOK_HANDLER = "webhook_handler"


@dataclass
class FlowTrigger:
    """Defines what triggers a flow"""
    trigger_type: TriggerType
    trigger_id: str  # webhook name, signal name, event type, etc.
    conditions: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowHandler:
    """Defines what handles a triggered flow"""
    handler_type: HandlerType
    handler_path: str  # dotted path or registry key
    parameters: Dict[str, Any] = field(default_factory=dict)
    retry_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowDefinition:
    """Complete flow definition"""
    flow_id: str
    name: str
    description: str
    trigger: FlowTrigger
    handlers: List[FlowHandler]
    enabled: bool = True
    tenant_id: Optional[str] = None
    created_by: Optional[str] = None


class FlowConnector:
    """Main flow connector that manages flow configurations and execution"""
    
    def __init__(self):
        self.flows: Dict[str, FlowDefinition] = {}
        self.trigger_registry: Dict[str, List[str]] = defaultdict(list)
        self.manual_trigger_index: Dict[str, str] = {}
        self._setup_event_listeners()
    
    def register_flow(self, flow_definition: FlowDefinition) -> None:
        """Register a new flow"""
        self.flows[flow_definition.flow_id] = flow_definition
        
        # Register with appropriate trigger system
        self._register_trigger(flow_definition)
        
        logger.info(f"Registered flow: {flow_definition.flow_id}")
    
    def unregister_flow(self, flow_id: str) -> None:
        """Unregister a flow"""
        if flow_id in self.flows:
            flow = self.flows[flow_id]
            self._unregister_trigger(flow)
            del self.flows[flow_id]
            logger.info(f"Unregistered flow: {flow_id}")
    
    def _register_trigger(self, flow: FlowDefinition) -> None:
        """Register flow trigger with appropriate system"""
        trigger = flow.trigger
        
        if trigger.trigger_type == TriggerType.EVENT:
            # Register with event bus
            event_bus.subscribe(trigger.trigger_id, 
                              lambda *args, **kwargs: self._execute_flow(flow.flow_id, *args, **kwargs))
        
        elif trigger.trigger_type == TriggerType.WEBHOOK:
            # Register webhook trigger mapping
            self.trigger_registry[f"webhook:{trigger.trigger_id}"].append(flow.flow_id)
        
        elif trigger.trigger_type == TriggerType.SCHEDULED:
            # Register scheduled task trigger mapping
            self.trigger_registry[f"scheduled:{trigger.trigger_id}"].append(flow.flow_id)

        elif trigger.trigger_type == TriggerType.MANUAL:
            manual_key = trigger.trigger_id or f"manual:{flow.flow_id}"
            if not str(manual_key).startswith("manual:"):
                manual_key = f"manual:{manual_key}"
            canonical_key = f"manual:{flow.flow_id}"
            self.manual_trigger_index[flow.flow_id] = str(manual_key)
            for key in {str(manual_key), canonical_key}:
                if flow.flow_id not in self.trigger_registry[key]:
                    self.trigger_registry[key].append(flow.flow_id)
    
    def _unregister_trigger(self, flow: FlowDefinition) -> None:
        """Unregister flow trigger"""
        trigger = flow.trigger
        
        if trigger.trigger_type == TriggerType.EVENT:
            # Note: EventBus doesn't have unsubscribe by flow_id, 
            # would need to track callback references
            pass
        
        # Remove from trigger registry
        if trigger.trigger_type == TriggerType.MANUAL:
            manual_key = self.manual_trigger_index.pop(flow.flow_id, None)
            canonical_key = f"manual:{flow.flow_id}"
            for key in {manual_key, canonical_key}:
                if not key:
                    continue
                flow_ids = self.trigger_registry.get(key)
                if flow_ids and flow.flow_id in flow_ids:
                    flow_ids.remove(flow.flow_id)
                    if not flow_ids:
                        self.trigger_registry.pop(key, None)
            return

        trigger_key = f"{trigger.trigger_type.value}:{trigger.trigger_id}"
        if trigger_key in self.trigger_registry:
            if flow.flow_id in self.trigger_registry[trigger_key]:
                self.trigger_registry[trigger_key].remove(flow.flow_id)
    
    def trigger_webhook_flows(self, webhook_name: str, payload: Dict[str, Any]) -> None:
        """Trigger flows for webhook events"""
        trigger_key = f"webhook:{webhook_name}"
        flow_ids = self.trigger_registry.get(trigger_key, [])
        
        for flow_id in flow_ids:
            if flow_id in self.flows and self.flows[flow_id].enabled:
                self._execute_flow(flow_id, webhook_payload=payload)
    
    def trigger_scheduled_flows(self, schedule_name: str, **kwargs) -> None:
        """Trigger flows for scheduled events"""
        trigger_key = f"scheduled:{schedule_name}"
        flow_ids = self.trigger_registry.get(trigger_key, [])

        for flow_id in flow_ids:
            if flow_id in self.flows and self.flows[flow_id].enabled:
                self._execute_flow(flow_id, **kwargs)

    def trigger_manual_flow(self, flow_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Trigger a flow that was registered with a manual trigger."""

        detail: Dict[str, Any] = {
            "flow_id": flow_id,
            "canonical_key": f"manual:{flow_id}",
            "trigger_key": self.manual_trigger_index.get(flow_id),
            "triggered": False,
        }

        flow = self.flows.get(flow_id)
        if not flow:
            detail["reason"] = "not_registered"
            logger.warning("Manual trigger requested for unknown flow %s", flow_id)
            return detail

        if not flow.enabled:
            detail["reason"] = "disabled"
            logger.debug("Manual trigger skipped for disabled flow %s", flow_id)
            return detail

        logger.info("Manually triggering flow: %s", flow_id)
        result = self._execute_flow(flow_id, payload=payload or {})
        detail.update({
            "triggered": True,
            "result": result,
        })
        return detail
    
    def _execute_flow(self, flow_id: str, *args, **kwargs) -> Any:
        """Execute a flow by running its handlers"""
        if flow_id not in self.flows:
            logger.error(f"Flow not found: {flow_id}")
            return
        
        flow = self.flows[flow_id]
        if not flow.enabled:
            logger.debug(f"Flow disabled: {flow_id}")
            return
        
        logger.info(f"Executing flow: {flow_id}")
        
        # Check trigger conditions
        if not self._check_conditions(flow.trigger.conditions, *args, **kwargs):
            logger.debug(f"Flow conditions not met: {flow_id}")
            return
        
        # Execute handlers in sequence
        last_result: Any = None
        for handler in flow.handlers:
            try:
                result = self._execute_handler(handler, flow_id, *args, **kwargs)
                if result is not None:
                    last_result = result
            except Exception as e:
                logger.error(f"Handler execution failed in flow {flow_id}: {e}")
                # Continue with next handler or implement failure handling
        return last_result

    def _execute_handler(self, handler: FlowHandler, flow_id: str, *args, **kwargs) -> Any:
        """Execute a specific handler"""
        try:
            if handler.handler_type == HandlerType.TASK:
                # Execute Celery task
                task_func = get_handler(handler.handler_path)
                task_func.apply_async(args=args, kwargs={**kwargs, **handler.parameters})

            elif handler.handler_type == HandlerType.SHARED_TASK:
                # Execute shared task
                task_func = get_handler(handler.handler_path)
                task_func.apply_async(args=args, kwargs={**kwargs, **handler.parameters})

            elif handler.handler_type == HandlerType.FUNCTION:
                # Execute regular function
                func = get_handler(handler.handler_path)
                return func(*args, **kwargs, **handler.parameters)

            elif handler.handler_type == HandlerType.WEBHOOK_HANDLER:
                # Execute webhook handler
                handler_func = get_handler(handler.handler_path)
                return handler_func(*args, **kwargs, **handler.parameters)
            
            elif handler.handler_type == HandlerType.AGENT:
                executor_path = handler.parameters.get(
                    "executor_path",
                    "flows.core.agent_runtime.AgentFlowExecutor",
                )
                if executor_path and executor_path != AgentFlowExecutor.__module__ + "." + AgentFlowExecutor.__name__:
                    executor_cls = import_string(executor_path)
                else:
                    executor_cls = AgentFlowExecutor

                executor = executor_cls()
                try:
                    return executor.execute(
                        handler.parameters,
                        flow_id=flow_id,
                        trigger_args=args,
                        trigger_kwargs=kwargs,
                    )
                except FlowAgentExecutionError as exc:
                    logger.error(
                        "Agent handler failed for flow %s (%s): %s",
                        flow_id,
                        handler.handler_path,
                        exc,
                        exc_info=True,
                    )
                
        except Exception as e:
            logger.error(f"Handler execution error: {e}")
            raise
    
    def _check_conditions(self, conditions: Dict[str, Any], *args, **kwargs) -> bool:
        """Check if trigger conditions are met"""
        if not conditions:
            return True
        
        # Implement condition checking logic
        # For example: check payload fields, instance attributes, etc.
        return True
    
    def _setup_event_listeners(self) -> None:
        """Setup listeners for various event sources"""
        # This could be extended to automatically listen to common events
        pass
    
    def get_flows_by_trigger(self, trigger_type: TriggerType, trigger_id: str) -> List[FlowDefinition]:
        """Get all flows for a specific trigger"""
        return [flow for flow in self.flows.values() 
                if flow.trigger.trigger_type == trigger_type 
                and flow.trigger.trigger_id == trigger_id]
    
    def list_flows(self, tenant_id: Optional[str] = None) -> List[FlowDefinition]:
        """List all flows, optionally filtered by tenant"""
        flows = list(self.flows.values())
        if tenant_id:
            flows = [f for f in flows if f.tenant_id == tenant_id]
        return flows


# Global flow connector instance
flow_connector = FlowConnector()


def trigger_manual_flow(flow_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience wrapper to trigger a manual flow on the shared connector."""

    return flow_connector.trigger_manual_flow(flow_id, payload)


__all__ = [
    "FlowConnector",
    "FlowDefinition",
    "FlowHandler",
    "FlowTrigger",
    "HandlerType",
    "TriggerType",
    "flow_connector",
    "trigger_manual_flow",
]
