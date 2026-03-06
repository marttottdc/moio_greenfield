
"""
Example flow configurations showing how to use the flow connector system
"""

from flows.core.management import flow_manager
from flows.core.connector import HandlerType, TriggerType


def setup_example_flows():
    """Setup some example flows"""
    
    # Example 1: Webhook flow for new orders
    flow_manager.create_webhook_flow(
        flow_id="webhook_new_order",
        name="Process New Order",
        webhook_name="new_order",
        handler_path="chatbot.tasks.handle_received_order",
        handler_type=HandlerType.SHARED_TASK,
        conditions={"order_status": "new"},
        parameters={"priority": "high"}
    )
    
    # Example 2: Signal flow for chat session end
    flow_manager.create_signal_flow(
        flow_id="signal_session_ended",
        name="Process Session End",
        signal_name="post_save.chatbot.ChatbotSession",
        handler_path="chatbot.tasks.session_ended_task",
        handler_type=HandlerType.TASK,
        conditions={"active": False}
    )
    
    # Example 3: Scheduled flow for email sync
    flow_manager.create_scheduled_flow(
        flow_id="scheduled_email_sync",
        name="Sync Email Accounts",
        schedule_name="daily_email_sync",
        handler_path="chatbot.tasks.sync_all_email_accounts",
        handler_type=HandlerType.SHARED_TASK
    )
    
    # Example 4: Complex flow with multiple handlers
    from flows.core.connector import FlowDefinition, FlowTrigger, FlowHandler
    
    trigger = FlowTrigger(
        trigger_type=TriggerType.WEBHOOK,
        trigger_id="user_registration",
        conditions={"user_type": "premium"}
    )
    
    handlers = [
        FlowHandler(
            handler_type=HandlerType.TASK,
            handler_path="crm.tasks.create_customer_record",
            parameters={"source": "webhook"}
        ),
        FlowHandler(
            handler_type=HandlerType.TASK,
            handler_path="chatbot.tasks.send_welcome_message",
            parameters={"template": "premium_welcome"}
        ),
        FlowHandler(
            handler_type=HandlerType.FUNCTION,
            handler_path="portal.core.tools.log_user_event",
            parameters={"event_type": "registration"}
        )
    ]
    
    complex_flow = FlowDefinition(
        flow_id="complex_user_registration",
        name="Premium User Registration Flow",
        description="Multi-step flow for premium user registration",
        trigger=trigger,
        handlers=handlers
    )
    
    flow_manager.connector.register_flow(complex_flow)


def setup_tenant_specific_flows(tenant_id: str):
    """Setup flows for a specific tenant"""
    
    # Tenant-specific webhook flow
    flow_manager.create_webhook_flow(
        flow_id=f"tenant_{tenant_id}_webhook_order",
        name=f"Tenant {tenant_id} Order Processing",
        webhook_name="order_received",
        handler_path="crm.tasks.process_tenant_order",
        handler_type=HandlerType.SHARED_TASK,
        parameters={"tenant_id": tenant_id},
        tenant_id=tenant_id
    )


if __name__ == "__main__":
    # Example usage
    setup_example_flows()
    
    # List all flows
    flows = flow_manager.connector.list_flows()
    for flow in flows:
        print(f"Flow: {flow.name} ({flow.flow_id})")
        print(f"  Trigger: {flow.trigger.trigger_type.value}:{flow.trigger.trigger_id}")
        print(f"  Handlers: {len(flow.handlers)}")
        print()
