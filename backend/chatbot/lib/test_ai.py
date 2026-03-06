from moio_platform.lib.openai_gpt_api import get_simple_response, get_json_response

response = get_simple_response("estas ahi ?", model="gpt-4-1106-preview")
print(response)

get_json_response("listar los años en que hubo juegos olimpicos y la ciudad donde se jugaron responder con un objeto json",  model="gpt-4-1106-preview")