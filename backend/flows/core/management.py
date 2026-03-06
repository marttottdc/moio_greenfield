
from typing import Dict, Any, List
import json
from flows.core.connector import (
    FlowConnector, FlowDefinition, FlowTrigger, FlowHandler,
    TriggerType, HandlerType, flow_connector
)


class FlowManager:
    """High-level flow management utilities"""
    
    def __init__(self, connector: FlowConnector = None):
        self.connector = connector or flow_connector
    
    def create_webhook_flow(self, 
                           flow_id: str,
                           name: str,
                           webhook_name: str,
                           handler_path: str,
                           handler_type: HandlerType = HandlerType.TASK,
                           conditions: Dict[str, Any] = None,
                           parameters: Dict[str, Any] = None,
                           tenant_id: str = None) -> FlowDefinition:
        """Create a webhook-triggered flow"""
        
        trigger = FlowTrigger(
            trigger_type=TriggerType.WEBHOOK,
            trigger_id=webhook_name,
            conditions=conditions or {}
        )
        
        handler = FlowHandler(
            handler_type=handler_type,
            handler_path=handler_path,
            parameters=parameters or {}
        )
        
        flow = FlowDefinition(
            flow_id=flow_id,
            name=name,
            description=f"Webhook flow for {webhook_name}",
            trigger=trigger,
            handlers=[handler],
            tenant_id=tenant_id
        )
        
        self.connector.register_flow(flow)
        return flow
    
    def create_signal_flow(self,
                          flow_id: str,
                          name: str,
                          signal_name: str,
                          handler_path: str,
                          handler_type: HandlerType = HandlerType.TASK,
                          conditions: Dict[str, Any] = None,
                          parameters: Dict[str, Any] = None,
                          tenant_id: str = None) -> FlowDefinition:
        """Create a signal-triggered flow"""
        
        trigger = FlowTrigger(
            trigger_type=TriggerType.SIGNAL,
            trigger_id=signal_name,
            conditions=conditions or {}
        )
        
        handler = FlowHandler(
            handler_type=handler_type,
            handler_path=handler_path,
            parameters=parameters or {}
        )
        
        flow = FlowDefinition(
            flow_id=flow_id,
            name=name,
            description=f"Signal flow for {signal_name}",
            trigger=trigger,
            handlers=[handler],
            tenant_id=tenant_id
        )
        
        self.connector.register_flow(flow)
        return flow
    
    def create_scheduled_flow(self,
                             flow_id: str,
                             name: str,
                             schedule_name: str,
                             handler_path: str,
                             handler_type: HandlerType = HandlerType.TASK,
                             parameters: Dict[str, Any] = None,
                             tenant_id: str = None) -> FlowDefinition:
        """Create a scheduled flow"""
        
        trigger = FlowTrigger(
            trigger_type=TriggerType.SCHEDULED,
            trigger_id=schedule_name
        )
        
        handler = FlowHandler(
            handler_type=handler_type,
            handler_path=handler_path,
            parameters=parameters or {}
        )
        
        flow = FlowDefinition(
            flow_id=flow_id,
            name=name,
            description=f"Scheduled flow: {schedule_name}",
            trigger=trigger,
            handlers=[handler],
            tenant_id=tenant_id
        )
        
        self.connector.register_flow(flow)
        return flow
    
    def export_flows(self, tenant_id: str = None) -> str:
        """Export flows to JSON"""
        flows = self.connector.list_flows(tenant_id)
        flow_data = []
        
        for flow in flows:
            flow_dict = {
                'flow_id': flow.flow_id,
                'name': flow.name,
                'description': flow.description,
                'enabled': flow.enabled,
                'tenant_id': flow.tenant_id,
                'trigger': {
                    'trigger_type': flow.trigger.trigger_type.value,
                    'trigger_id': flow.trigger.trigger_id,
                    'conditions': flow.trigger.conditions,
                    'metadata': flow.trigger.metadata
                },
                'handlers': [{
                    'handler_type': h.handler_type.value,
                    'handler_path': h.handler_path,
                    'parameters': h.parameters,
                    'retry_config': h.retry_config
                } for h in flow.handlers]
            }
            flow_data.append(flow_dict)
        
        return json.dumps(flow_data, indent=2)
    
    def import_flows(self, json_data: str) -> List[FlowDefinition]:
        """Import flows from JSON"""
        flow_data = json.loads(json_data)
        imported_flows = []
        
        for data in flow_data:
            trigger = FlowTrigger(
                trigger_type=TriggerType(data['trigger']['trigger_type']),
                trigger_id=data['trigger']['trigger_id'],
                conditions=data['trigger']['conditions'],
                metadata=data['trigger']['metadata']
            )
            
            handlers = []
            for h_data in data['handlers']:
                handler = FlowHandler(
                    handler_type=HandlerType(h_data['handler_type']),
                    handler_path=h_data['handler_path'],
                    parameters=h_data['parameters'],
                    retry_config=h_data['retry_config']
                )
                handlers.append(handler)
            
            flow = FlowDefinition(
                flow_id=data['flow_id'],
                name=data['name'],
                description=data['description'],
                trigger=trigger,
                handlers=handlers,
                enabled=data['enabled'],
                tenant_id=data['tenant_id']
            )
            
            self.connector.register_flow(flow)
            imported_flows.append(flow)
        
        return imported_flows


# Global flow manager instance
flow_manager = FlowManager()
