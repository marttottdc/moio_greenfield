
import json
from typing import Optional, Dict, Any, List
from django.db import transaction

from chatbot.models.agent_configuration import AgentConfiguration
from central_hub.context_utils import current_tenant


class AgentService:
    """Business logic for AI Agent Configuration operations"""
    
    @staticmethod
    def create_agent(tenant, name: str, model: str = 'gpt-4o-mini', 
                    instructions: str = '', channel: str = '', 
                    channel_id: str = '', tools_json: str = '{}', 
                    enabled: bool = True) -> tuple[Optional[AgentConfiguration], str]:
        """
        Create a new AI agent configuration
        Returns (agent, message)
        """
        try:
            with transaction.atomic():
                # Parse tools JSON, fallback to empty dict if invalid
                try:
                    tools = json.loads(tools_json) if tools_json.strip() else {}
                except json.JSONDecodeError:
                    tools = {}

                # Set tenant context for TenantManager filtering
                token = current_tenant.set(tenant)
                try:
                    agent = AgentConfiguration.objects.create(
                        tenant=tenant,
                        name=name,
                        model=model,
                        instructions=instructions,
                        channel=channel,
                        channel_id=channel_id,
                        tools=tools,
                        enabled=enabled
                    )
                finally:
                    current_tenant.reset(token)
                
                return agent, f"Agent '{name}' created successfully."
                
        except Exception as e:
            return None, f"Error creating agent: {str(e)}"
    
    @staticmethod
    def update_agent(agent: AgentConfiguration, name: str, model: str, 
                    instructions: str, channel: str, channel_id: str, 
                    tools_json: str, enabled: bool) -> tuple[bool, str]:
        """
        Update an existing agent configuration
        Returns (success, message)
        """
        try:
            with transaction.atomic():
                agent.name = name
                agent.model = model
                agent.instructions = instructions
                agent.channel = channel
                agent.channel_id = channel_id
                agent.enabled = enabled
                
                # Parse tools JSON, fallback to existing tools if invalid
                try:
                    agent.tools = json.loads(tools_json) if tools_json.strip() else {}
                except json.JSONDecodeError:
                    pass  # Keep existing tools if JSON is invalid
                    
                agent.save()
                return True, f"Agent '{agent.name}' updated successfully."
                
        except Exception as e:
            return False, f"Error updating agent: {str(e)}"
    
    @staticmethod
    def delete_agent(agent_id: str, tenant) -> tuple[bool, str]:
        """
        Delete an agent configuration
        Returns (success, message)
        
        Note: AgentConfiguration uses TenantManager which automatically filters
        by current_tenant.get(). We set the tenant context to ensure correct filtering.
        """
        # Set tenant context for TenantManager filtering
        token = current_tenant.set(tenant)
        try:
            try:
                # TenantManager will automatically filter by the set tenant
                agent = AgentConfiguration.objects.get(id=agent_id)
                agent_name = agent.name
                agent.delete()
                return True, f"Agent '{agent_name}' deleted successfully."
            except AgentConfiguration.DoesNotExist:
                return False, "Agent configuration not found."
            except Exception as e:
                return False, f"Error deleting agent: {str(e)}"
        finally:
            current_tenant.reset(token)
    
    @staticmethod
    def get_agent_by_id(agent_id: str, tenant) -> Optional[AgentConfiguration]:
        """Get agent by ID for the tenant.
        
        Note: AgentConfiguration uses TenantManager which automatically filters
        by current_tenant.get(). We set the tenant context to ensure correct filtering.
        """
        # Set tenant context for TenantManager filtering
        token = current_tenant.set(tenant)
        try:
            # TenantManager will automatically filter by the set tenant
            return AgentConfiguration.objects.get(id=agent_id)
        except AgentConfiguration.DoesNotExist:
            return None
        finally:
            current_tenant.reset(token)
    
    @staticmethod
    def list_agents(tenant) -> List[AgentConfiguration]:
        """List all agents for tenant.
        
        Note: AgentConfiguration uses TenantManager which automatically filters
        by current_tenant.get(). The middleware should already set the tenant context,
        but we ensure it's set here explicitly to guarantee correct filtering.
        """
        # Explicitly set tenant context for TenantManager filtering
        # This ensures the context is set even if middleware didn't set it correctly
        token = current_tenant.set(tenant)
        try:
            # TenantManager will automatically filter by the set tenant
            agents = list(AgentConfiguration.objects.all())
            return agents
        finally:
            # Reset to previous context (middleware will handle final cleanup)
            current_tenant.reset(token)
