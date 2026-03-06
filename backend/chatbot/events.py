# chatbot/events.py

from websockets_app.services.publisher import WebSocketEventPublisher
from chatbot.serializers import (
    build_session_payload,
    build_message_payload,
)
from moio_platform.core.events import emit_event
from moio_platform.core.events.snapshots import snapshot_chatbot_session


def session_started(session):
    # Emit canonical communications event (all channels).
    try:
        tenant_code = session.tenant.tenant_code if getattr(session, "tenant", None) else None
        if tenant_code:
            session_snapshot = snapshot_chatbot_session(session, messages_limit=50)
            emit_event(
                name="communications.session_started",
                tenant_id=tenant_code,
                entity={"type": "chatbot_session", "id": str(session.pk)},
                payload={
                    "session_id": str(session.pk),
                    "contact_id": session_snapshot.get("contact_id"),
                    "channel": session_snapshot.get("channel"),
                    "started_at": session_snapshot.get("start"),
                    "active": session_snapshot.get("active"),
                    "context": session_snapshot.get("context") or {},
                    "contact": session_snapshot.get("contact"),
                    "session": session_snapshot,
                },
                source="chatbot",
            )
    except Exception:
        # Do not break websocket flow on event emission issues.
        pass

    # Websocket notifications (WhatsApp only)
    if session.channel != "whatsapp":
        return

    WebSocketEventPublisher.whatsapp_conversation_started(
        tenant_id=session.tenant_id,
        conversation_id=str(session.pk),
        conversation_data=build_session_payload(session),
    )


def session_ended(session):
    # Emit canonical communications event (all channels).
    try:
        tenant_code = session.tenant.tenant_code if getattr(session, "tenant", None) else None
        if tenant_code:
            session_snapshot = snapshot_chatbot_session(session, messages_limit=50)
            emit_event(
                name="communications.session_ended",
                tenant_id=tenant_code,
                entity={"type": "chatbot_session", "id": str(session.pk)},
                payload={
                    "session_id": str(session.pk),
                    "contact_id": session_snapshot.get("contact_id"),
                    "channel": session_snapshot.get("channel"),
                    "started_at": session_snapshot.get("start"),
                    "ended_at": session_snapshot.get("end"),
                    "active": session_snapshot.get("active"),
                    "context": session_snapshot.get("context") or {},
                    "final_summary": session_snapshot.get("final_summary"),
                    "csat": session_snapshot.get("csat"),
                    "messages_count": session_snapshot.get("messages_count"),
                    "messages": session_snapshot.get("messages"),
                    "contact": session_snapshot.get("contact"),
                    "session": session_snapshot,
                },
                source="chatbot",
            )
    except Exception:
        pass

    # Websocket notifications (WhatsApp only)
    if session.channel != "whatsapp":
        return

    WebSocketEventPublisher.whatsapp_conversation_ended(
        tenant_id=session.tenant_id,
        conversation_id=str(session.pk),
        conversation_data=build_session_payload(session),
    )


def message_received(message):
    session = message.session
    if session.channel != "whatsapp":
        return

    WebSocketEventPublisher.whatsapp_message_received(
        tenant_id=session.tenant_id,
        conversation_id=str(session.pk),
        message_data=build_message_payload(message),
    )


def message_sent(message):
    session = message.session
    if session.channel != "whatsapp":
        return

    WebSocketEventPublisher.whatsapp_message_sent(
        tenant_id=session.tenant_id,
        conversation_id=str(session.pk),
        message_data=build_message_payload(message),
    )
