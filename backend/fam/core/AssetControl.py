import json

from django.utils import timezone

"""

from transitions import Machine

class AssetManager(Machine):

    def __init__(self, contact: Contact, received_text: str, channel: str):

        self.contact = contact
        self.received_text = received_text
        self.last_assistant_message = ''
        self.channel = channel
        self.intent = None

        if channel == 'whatsapp':
            self.user_id = contact.get_phone
        elif channel == 'console':
            self.user_id = contact.email

        try:
            self.configuration = get_chatbot_configuration()

        except Exception as e:

            print('Chatbot Config is missing')

        try:
            self.session = ChatbotSession.objects.exclude(state="Closed").filter(user_id=self.user_id).latest('start')
            print(f'session: {self.session.pk} state: {self.session.state} ')

        except Exception as e:
            print(e)

            self.session = ChatbotSession(
                user_id=self.user_id,
                start=timezone.now(),
                last_interaction=timezone.now(),
                state='New',
                started_by='user',
                channel=channel

            )
            self.session.save()

        Machine.__init__(self, states=load_states(), transitions=load_transitions(), initial=self.session.state, auto_transitions=False, ignore_invalid_triggers=False)

        print(f"This machine is Live... state: {self.session.state} in session: {self.session.pk} ")
        if self.state == 'New':
            print(f'State: {self.state}..')
            self.setup()

        # Update session summary evey time the session is resumed
        else:
            self.add_dialog(content=self.received_text, role='user')
            response = summarize(self.load_gpt_conversation(), caller_id="Session.__update_context",
                                 session_id=self.session.pk)

            if response is not None:

                if self.contact.get_fullname == "" and response["fullname"] != "":
                    self.contact.fullname = response["fullname"]

                if self.contact.get_email == "" and response["email"] != "":
                    self.contact.email = response["email"]

                if self.contact.get_company == "" and response["company"] != "":
                    self.contact.company = response["company"]

                print(f'intent of summary: {response["intent"]}')
                print(f'summary: {response["summary"]}')

                self.session.summary = response["summary"]
                self.session.save()

"""