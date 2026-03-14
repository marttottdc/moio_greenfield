from django.contrib import admin

from chatbot.models.chatbot_configuration import ChatbotConfiguration
from chatbot.models.agent_session import AgentSession, SessionThread
from chatbot.models.openai_configuration import OpenaiConfiguration
# from chatbot.models.assessment_data import PainPoint, Campaign, AssessmentInstance, AssessmentQuestion,    AssessmentQuestionOption, AssessmentInstanceResponseVector

from chatbot.models.wa_message_log import WaMessageLog
from chatbot.models.wa_payloads import WaPayloads
from chatbot.models.wa_templates import WaTemplate, WaTemplateComponent
from chatbot.models.email_data import EmailMessage, EmailAccount
from chatbot.models.agent_configuration import AgentConfiguration
from chatbot.models.tenant_chatbot_settings import TenantChatbotSettings


class SessionThreadAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'role', 'content', 'created')


class AgentSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'contact', 'last_interaction', 'active', 'final_summary', 'end')
    list_filter = ['active', 'tenant']
    search_fields = ['contact__fullname', 'id']


class WaMessageLogAdmin(admin.ModelAdmin):
    list_display = ('pk', 'tenant', 'type', 'timestamp', 'status', 'msg_id', 'user_number')
    list_filter = ['status']
    search_fields = ['msg_id']

# Register your models here


admin.site.register(ChatbotConfiguration)
admin.site.register(AgentSession, AgentSessionAdmin)
admin.site.register(SessionThread, SessionThreadAdmin)


admin.site.register(WaPayloads)
admin.site.register(WaMessageLog, WaMessageLogAdmin)
admin.site.register(OpenaiConfiguration)
admin.site.register(WaTemplate)
admin.site.register(WaTemplateComponent)

#admin.site.register(PainPoint)
#admin.site.register(Campaign)
#admin.site.register(AssessmentInstance)
#admin.site.register(AssessmentInstanceResponseVector)
#admin.site.register(AssessmentQuestion)
#admin.site.register(AssessmentQuestionOption)

admin.site.register(EmailMessage)
admin.site.register(EmailAccount)
admin.site.register(AgentConfiguration)
admin.site.register(TenantChatbotSettings)
