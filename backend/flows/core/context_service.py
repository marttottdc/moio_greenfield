"""FlowAgentContext service for managing shared agentic context."""
import logging
from typing import Any, Dict, List, Optional
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class FlowAgentContextService:
    """
    Service for managing FlowAgentContext lifecycle and operations.
    
    Handles:
    - Context creation/retrieval per flow execution
    - Recording agent turns with proper indexing
    - Merging variables and conversation history
    - Transactional updates to prevent race conditions
    """
    
    @staticmethod
    def get_or_create_context(flow_execution, tenant):
        """
        Get existing context for an execution or create a new one.
        
        Args:
            flow_execution: The FlowExecution instance
            tenant: The Tenant instance
            
        Returns:
            Tuple of (FlowAgentContext, created: bool)
        """
        try:
            from flows.models import FlowAgentContext
            
            context, created = FlowAgentContext.objects.get_or_create(
                flow_execution=flow_execution,
                defaults={
                    'tenant': tenant,
                    'shared_variables': {},
                    'conversation_history': [],
                    'tool_calls_log': [],
                }
            )
            
            if created:
                logger.debug(f"Created new FlowAgentContext for execution {flow_execution.id}")
            else:
                logger.debug(f"Retrieved existing FlowAgentContext for execution {flow_execution.id}")
                
            return context, created
            
        except Exception as e:
            logger.error(f"Error getting/creating FlowAgentContext: {e}")
            raise
    
    @staticmethod
    def start_turn(context, agent_name: str, node_id: str = '', input_payload: Dict = None):
        """
        Start a new agent turn within the context.
        
        Args:
            context: The FlowAgentContext instance
            agent_name: Name of the agent executing
            node_id: ID of the flow node triggering this turn
            input_payload: Input data for the agent
            
        Returns:
            FlowAgentTurn instance
        """
        try:
            from flows.models import FlowAgentTurn
            
            with transaction.atomic():
                # Get next run index
                last_turn = context.turns.order_by('-run_index').first()
                next_index = (last_turn.run_index + 1) if last_turn else 0
                
                turn = FlowAgentTurn.objects.create(
                    context=context,
                    run_index=next_index,
                    agent_name=agent_name,
                    node_id=node_id,
                    input_payload=input_payload or {},
                    status=FlowAgentTurn.STATUS_RUNNING,
                )
                
                logger.debug(f"Started turn {next_index} for agent '{agent_name}'")
                return turn
                
        except Exception as e:
            logger.error(f"Error starting agent turn: {e}")
            raise
    
    @staticmethod
    def complete_turn(
        turn,
        output_payload: Dict = None,
        tool_calls: List[Dict] = None,
        messages: List[Dict] = None,
        merge_variables: Dict = None,
    ):
        """
        Complete an agent turn and update the shared context.
        
        Args:
            turn: The FlowAgentTurn instance
            output_payload: Output from the agent
            tool_calls: List of tool calls made
            messages: Conversation messages from this turn
            merge_variables: Variables to merge into shared context
        """
        try:
            from copy import deepcopy
            
            with transaction.atomic():
                # Refresh context from DB to get latest state (avoids concurrent overwrites)
                context = turn.context
                context.refresh_from_db()
                
                # Update turn with copies of data to prevent caller mutation
                turn.output_payload = deepcopy(output_payload) if output_payload else {}
                turn.tool_calls = deepcopy(tool_calls) if tool_calls else []
                turn.messages = deepcopy(messages) if messages else []
                turn.status = turn.STATUS_COMPLETED
                turn.completed_at = timezone.now()
                if turn.started_at:
                    turn.duration_ms = int((turn.completed_at - turn.started_at).total_seconds() * 1000)
                turn.save()
                
                # Update shared context (append methods now copy internally)
                if messages:
                    for msg in messages:
                        context.append_conversation(
                            role=msg.get('role', 'assistant'),
                            content=msg.get('content', ''),
                            agent_name=turn.agent_name
                        )
                
                if tool_calls:
                    for tc in tool_calls:
                        context.append_tool_call(
                            tool_name=tc.get('name', 'unknown'),
                            args=tc.get('args', {}),
                            result=tc.get('result'),
                            latency_ms=tc.get('latency_ms'),
                            agent_name=turn.agent_name
                        )
                
                if merge_variables:
                    context.merge_variables(merge_variables)
                
                # Save with specific fields to avoid overwriting concurrent changes
                context.save(update_fields=[
                    'conversation_history', 
                    'tool_calls_log', 
                    'shared_variables'
                ])
                
                logger.debug(f"Completed turn {turn.run_index} for agent '{turn.agent_name}'")
                
        except Exception as e:
            logger.error(f"Error completing agent turn: {e}")
            raise
    
    @staticmethod
    def fail_turn(turn, error: str):
        """
        Mark a turn as failed.
        
        Args:
            turn: The FlowAgentTurn instance
            error: Error message
        """
        try:
            turn.mark_failed(error)
            logger.warning(f"Turn {turn.run_index} failed: {error}")
        except Exception as e:
            logger.error(f"Error marking turn as failed: {e}")
            raise
    
    @staticmethod
    def get_conversation_history(context) -> List[Dict]:
        """Get the full conversation history from the context."""
        return context.conversation_history or []
    
    @staticmethod
    def get_shared_variables(context) -> Dict:
        """Get the current shared variables."""
        return context.shared_variables or {}
    
    @staticmethod
    def complete_context(context):
        """Mark the context as completed."""
        try:
            context.mark_completed()
            logger.debug(f"Marked context {context.id} as completed")
        except Exception as e:
            logger.error(f"Error completing context: {e}")
            raise
    
    @staticmethod
    def fail_context(context):
        """Mark the context as failed."""
        try:
            context.mark_failed()
            logger.warning(f"Marked context {context.id} as failed")
        except Exception as e:
            logger.error(f"Error marking context as failed: {e}")
            raise
