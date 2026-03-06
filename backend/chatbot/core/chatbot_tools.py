from chatbot.models.chatbot_session import ChatbotSession, ChatbotMemory
from crm.models import Contact


def print_sessions():

    sessions = ChatbotSession.objects.all()
    for s in sessions:
        print(s.session,
              s.tenant,
              s.user_id,
              s.started_by,
              s.start,
              s.active,
              s.human_mode,
              s.last_interaction)

        memo = ChatbotMemory.objects.filter(session=s.session)
        for m in memo:
            print(m.content, m.author, m.role, m.created)


        print('------------------------------------------')


def delete_sessions():

    sessions = ChatbotSession.objects.all()
    for s in sessions:
        print(s.session,
              s.tenant,
              s.user_id,
              s.started_by,
              s.start,
              s.active,
              s.human_mode,
              s.last_interaction)

        memo = ChatbotMemory.objects.filter(session=s.session)
        for m in memo:
            print(m.content, m.author, m.role, m.created)
            m.delete()
        s.delete()
        print('------------------------------------------')


def print_contacts():
    contacts = Contact.objects.all()
    for c in contacts:
        print(c.phone, c.email, c.fullname, c.pk)


