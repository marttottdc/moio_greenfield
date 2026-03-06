import asyncio
from agents import Runner

from agents import set_default_openai_key
from portal.models import TenantConfiguration
from chatbot.agents.moio_agents_loader import build_agents_for_tenant

config = TenantConfiguration.objects.get(tenant=1)
set_default_openai_key(config.openai_api_key)
# agents_team = AgentTeam("a555823f-76e7-4f68-85f4-1062037fc15e")

lista_de_agentes = build_agents_for_tenant(config.tenant)


def agent_tester():
    thread = []
    running_agent = lista_de_agentes["Main Agent"]

    while True:

        user_input = input(f"Ingresa tu necesidad ({len(thread)}):")
        user_utterance = {"role": "user", "content": user_input}
        thread.append(user_utterance)

        context = {
            "session": {
                "tenant_id": 1,
            },
            "contact": {
                "name": "Martin",
                "email": "marttott@hotmail.com",
                "phone": "+59191941411",
            },
            "summary": "",
        }

        try:

            # print(running_agent.handoffs)

            result = asyncio.run(Runner.run(running_agent, input=thread, context=context))

            print(result.final_output)
            print(f'Last agent: {result.last_agent.name}')

            # print(result.to_input_list())

            running_agent = lista_de_agentes[result.last_agent.name]

            assistant_utterance = {"role": "assistant", "content": str(result.final_output)}

            thread.append(assistant_utterance)
            print("-----------")

        except Exception as e:
            print(e)
