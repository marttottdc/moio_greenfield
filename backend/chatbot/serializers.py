from crm.serializers import ContactSerializer
from chatbot.models.chatbot_session import ChatbotSession, ChatbotMemory


def build_message_payload(message: ChatbotMemory):

    return {
        "id": str(message.pk),
        "session_id": str(message.session_id),
        "content": message.content,
        "role": message.role,
        "author": message.author,
        "created": message.created.isoformat(),
    }


def build_session_payload(session: ChatbotSession):
    contact_data = {}
    if session.contact:
        contact_data = ContactSerializer(session.contact).data

    return {
        "session_id": str(session.pk),
        "channel": session.channel,
        "active": session.active,
        "started_by": session.started_by,
        "start": session.start.isoformat() if session.start else None,
        "human_mode": session.human_mode,
        "contact": contact_data,
    }
