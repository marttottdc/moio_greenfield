import json
from moio_platform.lib.moio_assistant_functions import MoioAssistantTools


at = MoioAssistantTools("123", 16, None, "43423")

while True:
    search_term = input("Que quieres buscar?: ")
    search_results = at.search_knowledge(search_term)
    if len(search_results) > 2:
        results = json.loads(search_results)
        for res in results:
            print("-+" * 80)
            print(res)

    print("no encontre lo que buscas")

