from chatbot.models.agent_session import AgentSession, SessionThread
from crm.models import Contact


def print_sessions():
    sessions = AgentSession.objects.all()
    for s in sessions:
        print(str(s.pk),
              s.tenant,
              s.contact_id,
              s.started_by,
              s.start,
              s.active,
              s.human_mode,
              s.last_interaction)

        memo = SessionThread.objects.filter(session=s)
        for m in memo:
            print(m.content, m.author, m.role, m.created)

        print('------------------------------------------')


def delete_sessions():
    sessions = AgentSession.objects.all()
    for s in sessions:
        print(str(s.pk),
              s.tenant,
              s.contact_id,
              s.started_by,
              s.start,
              s.active,
              s.human_mode,
              s.last_interaction)

        memo = SessionThread.objects.filter(session=s)
        for m in memo:
            print(m.content, m.author, m.role, m.created)
            m.delete()
        s.delete()
        print('------------------------------------------')


def print_contacts():
    contacts = Contact.objects.all()
    for c in contacts:
        print(c.phone, c.email, c.fullname, c.pk)


