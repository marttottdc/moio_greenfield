from pydantic import BaseModel
from enum import Enum


# Enum para Status
class ConversationStatus(str, Enum):
    PENDING_ASSISTANT_RESPONSE = "pending_assistant_response"
    RE_ENGAGEMENT_REQUIRED = "re_engagement_required"
    USER_STOPPED_ANSWERING = "user_stopped_answering"
    ASSISTANT_REPETITIVE_UTTERANCES = "assistant_repetitive_utterances"
    END_CONVERSATION_REQUIRED = "end_conversation_required"


# Enum para Action
class ConversationRequiredAction(str, Enum):
    PRODUCE_RESPONSE = "produce_response"
    RE_ENGAGE = "re_engage"
    END_CONVERSATION = "end_conversation"


# Modelo personalizado para Summary
class ConversationSummary(BaseModel):
    personal_data: str
    main_topics: str
    solutions: str


# Modelo principal
class ConversationAnalysisModel(BaseModel):
    summary: ConversationSummary
    status: ConversationStatus
    action: ConversationRequiredAction
    message_to_send: str
