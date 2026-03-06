import logging
from typing import Optional
from uuid import UUID

from asgiref.sync import async_to_sync
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from chatbot.models.chatbot_session import ChatbotSession, ChatbotMemory
from chatbot.models.agent_configuration import AgentConfiguration, CHANNEL_DESKTOP
from chatbot.services.moio_runtime_service import (
    get_runtime_backend_for_user,
    runtime_initiator_from_user,
)
from portal.models import MoioUser

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_desktop_sessions(request: Request) -> Response:
    user = request.user
    tenant_id = getattr(user, 'tenant_id', None)
    
    if not tenant_id:
        return Response({"error": "Tenant not found"}, status=status.HTTP_400_BAD_REQUEST)
    
    from crm.models import Contact
    user_contact = Contact.objects.filter(tenant_id=tenant_id, email=user.email).first()
    
    if not user_contact:
        return Response({"sessions": []})
    
    sessions_qs = ChatbotSession.objects.filter(
        tenant_id=tenant_id,
        contact=user_contact,
        channel=CHANNEL_DESKTOP
    ).order_by('-last_interaction')
    
    sessions = []
    for session in sessions_qs[:50]:
        last_message = ChatbotMemory.objects.filter(
            session=session
        ).exclude(role='system').order_by('-created').first()
        
        sessions.append({
            "session_id": str(session.session),
            "active": session.active,
            "started_at": session.start.isoformat() if session.start else None,
            "last_interaction": session.last_interaction.isoformat() if session.last_interaction else None,
            "current_agent": session.current_agent,
            "last_message_preview": (last_message.content[:100] + "...") if last_message and len(last_message.content) > 100 else (last_message.content if last_message else None)
        })
    
    return Response({"sessions": sessions})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_session_history(request: Request, session_id: str) -> Response:
    user = request.user
    tenant_id = getattr(user, 'tenant_id', None)
    
    if not tenant_id:
        return Response({"error": "Tenant not found"}, status=status.HTTP_400_BAD_REQUEST)
    
    from crm.models import Contact
    user_contact = Contact.objects.filter(tenant_id=tenant_id, email=user.email).first()
    
    if not user_contact:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        session = ChatbotSession.objects.get(
            session=session_id,
            tenant_id=tenant_id,
            contact=user_contact,
            channel=CHANNEL_DESKTOP
        )
    except ChatbotSession.DoesNotExist:
        return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)
    
    messages = ChatbotMemory.objects.filter(
        session=session
    ).exclude(role='system').order_by('created')
    
    history = [
        {
            "role": msg.role,
            "content": msg.content,
            "author": msg.author,
            "timestamp": msg.created.isoformat()
        }
        for msg in messages
    ]
    
    return Response({
        "session_id": str(session.session),
        "active": session.active,
        "current_agent": session.current_agent,
        "messages": history
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def close_session(request: Request, session_id: str) -> Response:
    user = request.user
    tenant_id = getattr(user, 'tenant_id', None)
    
    if not tenant_id:
        return Response({"error": "Tenant not found"}, status=status.HTTP_400_BAD_REQUEST)
    
    from crm.models import Contact
    user_contact = Contact.objects.filter(tenant_id=tenant_id, email=user.email).first()
    
    if not user_contact:
        return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        session = ChatbotSession.objects.get(
            session=session_id,
            tenant_id=tenant_id,
            contact=user_contact,
            channel=CHANNEL_DESKTOP
        )
    except ChatbotSession.DoesNotExist:
        return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)
    
    session.active = False
    session.end = timezone.now()
    session.save(update_fields=['active', 'end'])
    
    return Response({
        "success": True,
        "session_id": str(session.session),
        "message": "Session closed successfully"
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_agent_status(request: Request) -> Response:
    user = request.user
    tenant_id = getattr(user, 'tenant_id', None)
    
    if not tenant_id:
        return Response({"error": "Tenant not found"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        moio_user = MoioUser.objects.get(pk=user.pk)
        preferences = moio_user.preferences or {}
        agent_id = preferences.get('crm_desktop_agent_id')
    except MoioUser.DoesNotExist:
        agent_id = None
    
    agent = None
    agent_source = None
    
    if agent_id:
        try:
            agent = AgentConfiguration.objects.get(
                id=agent_id,
                tenant_id=tenant_id,
                enabled=True
            )
            agent_source = "user_preference"
        except AgentConfiguration.DoesNotExist:
            pass
    
    if not agent:
        try:
            agent = AgentConfiguration.objects.get(
                tenant_id=tenant_id,
                default=True,
                enabled=True
            )
            agent_source = "default"
        except AgentConfiguration.DoesNotExist:
            pass
    
    if agent:
        return Response({
            "enabled": True,
            "agent": {
                "id": str(agent.id),
                "name": agent.name,
                "model": agent.model,
                "source": agent_source
            }
        })
    
    return Response({
        "enabled": False,
        "message": "No agent configured. Please set a CRM desktop agent in your preferences or configure a default agent."
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_available_agents(request: Request) -> Response:
    user = request.user
    tenant_id = getattr(user, 'tenant_id', None)
    
    if not tenant_id:
        return Response({"error": "Tenant not found"}, status=status.HTTP_400_BAD_REQUEST)
    
    agents = AgentConfiguration.objects.filter(
        tenant_id=tenant_id,
        enabled=True
    ).order_by('name')
    
    return Response({
        "agents": [
            {
                "id": str(agent.id),
                "name": agent.name,
                "model": agent.model,
                "is_default": agent.default
            }
            for agent in agents
        ]
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_user_agent(request: Request) -> Response:
    user = request.user
    tenant_id = getattr(user, 'tenant_id', None)
    
    if not tenant_id:
        return Response({"error": "Tenant not found"}, status=status.HTTP_400_BAD_REQUEST)
    
    agent_id = request.data.get('agent_id')
    
    if agent_id:
        try:
            agent = AgentConfiguration.objects.get(
                id=agent_id,
                tenant_id=tenant_id,
                enabled=True
            )
        except AgentConfiguration.DoesNotExist:
            return Response({"error": "Agent not found or not enabled"}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        moio_user = MoioUser.objects.get(pk=user.pk)
        preferences = moio_user.preferences or {}
        
        if agent_id:
            preferences['crm_desktop_agent_id'] = str(agent_id)
        else:
            preferences.pop('crm_desktop_agent_id', None)
        
        moio_user.preferences = preferences
        moio_user.save(update_fields=['preferences'])
        
        return Response({
            "success": True,
            "agent_id": str(agent_id) if agent_id else None,
            "message": "Agent preference updated successfully"
        })
    except MoioUser.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_runtime_resources(request: Request) -> Response:
    try:
        backend = get_runtime_backend_for_user(request.user)
        payload = async_to_sync(backend.resources)(
            initiator=runtime_initiator_from_user(request.user),
        )
        return Response(payload)
    except Exception as exc:
        logger.error("Failed to load moio runtime resources: %s", exc)
        return Response(
            {
                "ok": False,
                "error": str(exc),
                "message": "Moio runtime is not ready",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
