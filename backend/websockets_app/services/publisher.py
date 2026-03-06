import logging
from typing import Dict, Any, Optional, Union
from datetime import datetime
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


class WebSocketEventPublisher:
    
    @classmethod
    def _get_channel_layer(cls):
        return get_channel_layer()
    
    @classmethod
    def _normalize_id(cls, id_value: Union[str, UUID, int]) -> str:
        return str(id_value) if id_value else ""
    
    @classmethod
    def _build_event(cls, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'type': event_type,
            'payload': payload,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    @classmethod
    def publish_to_group(
        cls,
        group_name: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> bool:
        try:
            channel_layer = cls._get_channel_layer()
            if channel_layer is None:
                logger.warning("No channel layer configured")
                return False
            
            event = cls._build_event(event_type, payload)
            async_to_sync(channel_layer.group_send)(group_name, event)
            
            logger.debug(f"Published {event_type} to group {group_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish to group {group_name}: {e}")
            return False
    
    @classmethod
    def publish_ticket_event(
        cls,
        tenant_id: Union[str, UUID],
        event_type: str,
        ticket_data: Dict[str, Any],
        ticket_id: Optional[Union[str, UUID]] = None
    ) -> bool:
        tenant_str = cls._normalize_id(tenant_id)
        
        group_name = f"tickets_{tenant_str}"
        success = cls.publish_to_group(group_name, f"ticket_{event_type}", ticket_data)
        
        if ticket_id:
            ticket_group = f"ticket_{tenant_str}_{cls._normalize_id(ticket_id)}"
            cls.publish_to_group(ticket_group, f"ticket_{event_type}", ticket_data)
        
        return success
    
    @classmethod
    def ticket_created(cls, tenant_id: Union[str, UUID], ticket_data: Dict[str, Any]) -> bool:
        return cls.publish_ticket_event(tenant_id, "created", ticket_data, ticket_data.get('id'))
    
    @classmethod
    def ticket_updated(
        cls,
        tenant_id: Union[str, UUID],
        ticket_id: Union[str, UUID],
        ticket_data: Dict[str, Any]
    ) -> bool:
        return cls.publish_ticket_event(tenant_id, "updated", ticket_data, ticket_id)
    
    @classmethod
    def ticket_status_changed(
        cls,
        tenant_id: Union[str, UUID],
        ticket_id: Union[str, UUID],
        old_status: str,
        new_status: str,
        ticket_data: Dict[str, Any]
    ) -> bool:
        payload = {
            **ticket_data,
            'old_status': old_status,
            'new_status': new_status
        }
        return cls.publish_ticket_event(tenant_id, "status_changed", payload, ticket_id)
    
    @classmethod
    def ticket_assigned(
        cls,
        tenant_id: Union[str, UUID],
        ticket_id: Union[str, UUID],
        assignee_id: Union[str, UUID],
        assignee_name: str,
        ticket_data: Dict[str, Any]
    ) -> bool:
        payload = {
            **ticket_data,
            'assignee_id': cls._normalize_id(assignee_id),
            'assignee_name': assignee_name
        }
        return cls.publish_ticket_event(tenant_id, "assigned", payload, ticket_id)
    
    @classmethod
    def ticket_comment_added(
        cls,
        tenant_id: Union[str, UUID],
        ticket_id: Union[str, UUID],
        comment_data: Dict[str, Any]
    ) -> bool:
        return cls.publish_ticket_event(tenant_id, "comment_added", comment_data, ticket_id)
    
    @classmethod
    def publish_whatsapp_event(
        cls,
        tenant_id: Union[str, UUID],
        event_type: str,
        message_data: Dict[str, Any],
        conversation_id: Optional[Union[str, UUID]] = None
    ) -> bool:
        tenant_str = cls._normalize_id(tenant_id)
        
        group_name = f"whatsapp_{tenant_str}"
        success = cls.publish_to_group(group_name, event_type, message_data)
        
        if conversation_id:
            conv_group = f"whatsapp_conv_{tenant_str}_{cls._normalize_id(conversation_id)}"
            cls.publish_to_group(conv_group, event_type, message_data)
        
        return success
    
    @classmethod
    def whatsapp_conversation_started(
        cls,
        tenant_id: Union[str, UUID],
        conversation_data: Dict[str, Any],
        conversation_id: Optional[Union[str, UUID]] = None
    ) -> bool:
        return cls.publish_whatsapp_event(tenant_id, "conversation_started", conversation_data, conversation_id)

    @classmethod
    def whatsapp_conversation_ended(
            cls,
            tenant_id: Union[str, UUID],
            conversation_data: Dict[str, Any],
            conversation_id: Optional[Union[str, UUID]] = None
    ) -> bool:
        return cls.publish_whatsapp_event(tenant_id, "conversation_ended", conversation_data, conversation_id)

    @classmethod
    def whatsapp_message_received(
        cls,
        tenant_id: Union[str, UUID],
        message_data: Dict[str, Any],
        conversation_id: Optional[Union[str, UUID]] = None
    ) -> bool:
        return cls.publish_whatsapp_event(tenant_id, "message_received", message_data, conversation_id)
    
    @classmethod
    def whatsapp_message_sent(
        cls,
        tenant_id: Union[str, UUID],
        message_data: Dict[str, Any],
        conversation_id: Optional[Union[str, UUID]] = None
    ) -> bool:
        return cls.publish_whatsapp_event(tenant_id, "message_sent", message_data, conversation_id)
    
    @classmethod
    def whatsapp_message_delivered(
        cls,
        tenant_id: Union[str, UUID],
        message_id: Union[str, UUID],
        conversation_id: Optional[Union[str, UUID]] = None
    ) -> bool:
        return cls.publish_whatsapp_event(
            tenant_id, 
            "message_delivered", 
            {'message_id': cls._normalize_id(message_id)},
            conversation_id
        )
    
    @classmethod
    def whatsapp_message_read(
        cls,
        tenant_id: Union[str, UUID],
        message_id: Union[str, UUID],
        conversation_id: Optional[Union[str, UUID]] = None
    ) -> bool:
        return cls.publish_whatsapp_event(
            tenant_id,
            "message_read",
            {'message_id': cls._normalize_id(message_id)},
            conversation_id
        )


    @classmethod
    def publish_campaign_event(
        cls,
        tenant_id: Union[str, UUID],
        campaign_id: Union[str, UUID],
        event_type: str,
        payload: Dict[str, Any]
    ) -> bool:
        tenant_str = cls._normalize_id(tenant_id)
        campaign_str = cls._normalize_id(campaign_id)
        
        group_name = f"campaign_{tenant_str}_{campaign_str}"
        success = cls.publish_to_group(group_name, f"campaign_{event_type}", payload)
        
        tenant_group = f"campaigns_{tenant_str}"
        cls.publish_to_group(tenant_group, f"campaign_{event_type}", {
            **payload,
            'campaign_id': campaign_str
        })
        
        return success
    
    @classmethod
    def campaign_stats_updated(
        cls,
        tenant_id: Union[str, UUID],
        campaign_id: Union[str, UUID],
        stats: Dict[str, Any]
    ) -> bool:
        return cls.publish_campaign_event(tenant_id, campaign_id, "stats_updated", stats)
    
    @classmethod
    def campaign_status_changed(
        cls,
        tenant_id: Union[str, UUID],
        campaign_id: Union[str, UUID],
        old_status: str,
        new_status: str
    ) -> bool:
        return cls.publish_campaign_event(tenant_id, campaign_id, "status_changed", {
            'old_status': old_status,
            'new_status': new_status
        })
    
    @classmethod
    def campaign_message_sent(
        cls,
        tenant_id: Union[str, UUID],
        campaign_id: Union[str, UUID],
        recipient_data: Dict[str, Any]
    ) -> bool:
        return cls.publish_campaign_event(tenant_id, campaign_id, "message_sent", recipient_data)
    
    @classmethod
    def campaign_completed(
        cls,
        tenant_id: Union[str, UUID],
        campaign_id: Union[str, UUID],
        summary: Dict[str, Any]
    ) -> bool:
        return cls.publish_campaign_event(tenant_id, campaign_id, "completed", summary)
    
    @classmethod
    def publish_flow_preview_event(
        cls,
        tenant_id: Union[str, UUID],
        flow_id: Union[str, UUID],
        run_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> bool:
        tenant_str = cls._normalize_id(tenant_id)
        flow_str = cls._normalize_id(flow_id)
        
        event_payload = {
            'event_type': event_type,
            'payload': payload
        }
        
        run_group = f"flow_preview_{tenant_str}_{flow_str}_{run_id}"
        success = cls._publish_preview_event(run_group, event_payload)
        
        flow_group = f"flow_preview_{tenant_str}_{flow_str}"
        cls._publish_preview_event(flow_group, {**event_payload, 'payload': {**payload, 'run_id': run_id}})
        
        return success
    
    @classmethod
    def _publish_preview_event(cls, group_name: str, payload: Dict[str, Any]) -> bool:
        try:
            channel_layer = cls._get_channel_layer()
            if channel_layer is None:
                logger.warning("No channel layer configured")
                return False
            
            event = {
                'type': 'preview_event',
                'event_type': payload.get('event_type'),
                'payload': payload.get('payload', {}),
                'timestamp': datetime.utcnow().isoformat()
            }
            async_to_sync(channel_layer.group_send)(group_name, event)
            
            logger.debug(f"Published preview_event to group {group_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish preview event to group {group_name}: {e}")
            return False
    
    @classmethod
    def flow_preview_node_started(
        cls,
        tenant_id: Union[str, UUID],
        flow_id: Union[str, UUID],
        run_id: str,
        node_id: str,
        node_name: str
    ) -> bool:
        return cls.publish_flow_preview_event(tenant_id, flow_id, run_id, "node_started", {
            'node_id': node_id,
            'node_name': node_name
        })
    
    @classmethod
    def flow_preview_node_finished(
        cls,
        tenant_id: Union[str, UUID],
        flow_id: Union[str, UUID],
        run_id: str,
        node_id: str,
        node_name: str,
        output: Optional[Dict[str, Any]] = None
    ) -> bool:
        return cls.publish_flow_preview_event(tenant_id, flow_id, run_id, "node_finished", {
            'node_id': node_id,
            'node_name': node_name,
            'output': output or {}
        })
    
    @classmethod
    def flow_preview_node_error(
        cls,
        tenant_id: Union[str, UUID],
        flow_id: Union[str, UUID],
        run_id: str,
        node_id: str,
        node_name: str,
        error: str
    ) -> bool:
        return cls.publish_flow_preview_event(tenant_id, flow_id, run_id, "node_error", {
            'node_id': node_id,
            'node_name': node_name,
            'error': error
        })
    
    @classmethod
    def flow_preview_completed(
        cls,
        tenant_id: Union[str, UUID],
        flow_id: Union[str, UUID],
        run_id: str,
        status: str,
        summary: Optional[Dict[str, Any]] = None
    ) -> bool:
        return cls.publish_flow_preview_event(tenant_id, flow_id, run_id, "preview_completed", {
            'status': status,
            'summary': summary or {}
        })

    @classmethod
    def publish_robot_run_event(
        cls,
        tenant_id: Union[str, UUID],
        robot_id: Union[str, UUID],
        run_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> bool:
        tenant_str = cls._normalize_id(tenant_id)
        robot_str = cls._normalize_id(robot_id)

        event_payload = {
            "event_type": event_type,
            "payload": payload,
        }

        run_group = f"robot_run_{tenant_str}_{robot_str}_{run_id}"
        success = cls._publish_robot_event(run_group, event_payload)

        robot_group = f"robot_run_{tenant_str}_{robot_str}"
        cls._publish_robot_event(
            robot_group,
            {**event_payload, "payload": {**payload, "run_id": run_id}},
        )
        return success

    @classmethod
    def _publish_robot_event(cls, group_name: str, payload: Dict[str, Any]) -> bool:
        try:
            channel_layer = cls._get_channel_layer()
            if channel_layer is None:
                logger.warning("No channel layer configured")
                return False

            event = {
                "type": "robot_event",
                "event_type": payload.get("event_type"),
                "payload": payload.get("payload", {}),
                "timestamp": datetime.utcnow().isoformat(),
            }
            async_to_sync(channel_layer.group_send)(group_name, event)
            logger.debug(f"Published robot_event to group {group_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish robot event to group {group_name}: {e}")
            return False


