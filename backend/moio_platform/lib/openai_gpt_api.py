import base64
import json
import logging
import random
from io import BytesIO

from django.core.files.storage import default_storage
from openai import OpenAI, BaseModel

from central_hub.models import TenantConfiguration
import logging

try:
    from recruiter.core.gpt_tools import tools
except ModuleNotFoundError:
    tools = []

logger = logging.getLogger(__name__)

ASSISTANT_TOOL_TYPES = [{"type": "code_intepreter", "name": "Code Interpreter"},
                            {"type": "file_search", "name": "File Search"},]


class AssistantManager:
    def __init__(self, config: TenantConfiguration):

        self.client = OpenAI(api_key=config.openai_api_key)
        self.default_model = config.openai_default_model

    def create_assistant(self, name, instructions, description, selected_tools, model="gpt-4o"):

        assistant = self.client.beta.assistants.create(name=name,
                                                       description=description,
                                                       instructions=instructions,
                                                       model=model,
                                                       tools=selected_tools)

        print(assistant.id)

        return assistant

    def update_assistant(self, assistant_id, name, instructions, description, selected_tools: json, model="gpt-4o"):

        assistant = self.client.beta.assistants.update(
            assistant_id=assistant_id,
            name=name,
            description=description,
            instructions=instructions,
            model=model,
            tools=selected_tools
        )
        return assistant

    def list_assistants(self):
        return self.client.beta.assistants.list()

    def get_assistant(self, assistant_id):
        try:
            return self.client.beta.assistants.retrieve(assistant_id)

        except Exception as e:
            print(e)
            return None

    def get_models(self):
        try:
            return self.client.models.list()

        except Exception as e:
            raise RuntimeError(e)


class MoioOpenai:
    def __init__(self, api_key, default_model, max_retries=5, min_delay=1):
        """

        :param api_key:
        :param default_model:
        :param max_retries:
        :param min_delay:
        """

        self.client = OpenAI(api_key=api_key)
        self.default_model = default_model
        self.max_retries = max_retries
        self.min_delay = min_delay

    def get_available_models(self):
        try:

            return self.client.models.list()

        except Exception as e:

            raise RuntimeError(e)

    def simple_response(self, prompt, model=None, max_retries=None):
        """
        Acts as a regular chatgpt input, ask all you need in a single prompt
        :param prompt: the full request
        :param model: a valid OpenAI model
        :param max_retries: you guessed it!
        :return:
        """

        if model is None:
            model = self.default_model

        if max_retries is None:
            max_retries = self.max_retries

        for _ in range(int(max_retries)):

            try:

                completion = self.client.responses.create(
                    model=model,
                    input=prompt
                )

                return completion.output[0].content[0].text

            except Exception as e:
                logger.error(e)
                return None

        else:
            logger.error("Max retries exceeded")
            return None

    def get_embedding(self, text, model="text-embedding-3-small"):

        try:
            response = self.client.embeddings.create(
                input=text,
                model=model
            )

            return response.data[0].embedding

        except Exception as e:
            logger.error(e)
            return None

    def json_response(self, data, system_instructions="You are a helpful assistant designed to output JSON", max_retries=5):

        messages = [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": data}
        ]

        try:

            response = self.client.chat.completions.create(
                model=self.default_model,
                response_format={"type": "json_object"},
                messages=messages
            )

            data = response.choices[0].message.content

            return data

        except Exception as e:
            print('Openai Configuration Missing')
            return e

    @staticmethod
    def model_supports_structured_outputs(model: str) -> bool:
        """
        Structured Outputs (response_format json_schema / parse helpers) are only supported
        on GPT-4o family models and later snapshots (per OpenAI docs).
        """
        m = (model or "").strip().lower()
        # Conservative allowlist: treat anything outside GPT-4o as unsupported.
        return bool(m) and m.startswith("gpt-4o")

    def structured_parse_via_responses(
        self,
        data,
        system_instructions="You are a helpful assistant designed to output JSON",
        output_model=None,
        model="default",
        max_retries=5,
    ):
        """
        Return a parsed Pydantic object using the Responses API (client.responses.parse).
        Use when you want Responses API benefits (caching, recommended path). Falls back
        to structured_parse (Completions) if responses.parse is not available or fails.
        """
        if model == "default" or model is None:
            model = self.default_model
        if not self.model_supports_structured_outputs(model):
            raise ValueError("Configured Model does not support structured Outputs")
        if output_model is None:
            raise ValueError("output_model is required")

        last_exc = None
        for _ in range(int(max_retries or 1)):
            try:
                resp = self.client.responses.parse(
                    model=model,
                    instructions=system_instructions,
                    input=data if isinstance(data, str) else json.dumps(data),
                    text_format=output_model,
                )
                refusal = getattr(resp, "output_refusal", None)
                if refusal:
                    raise ValueError(f"openai_refusal:{refusal}")
                parsed = getattr(resp, "output_parsed", None)
                if parsed is not None:
                    return parsed
                # Fallback: raw output text -> validate
                output_text = getattr(resp, "output_text", None) or (resp.output and resp.output[0].content[0].text if getattr(resp, "output", None) else None)
                if output_text:
                    obj = json.loads(output_text) if isinstance(output_text, str) else output_text
                    return output_model.model_validate(obj)
                raise ValueError("openai_no_response")
            except AttributeError as e:
                # responses.parse or text_format may not exist in this SDK version
                last_exc = e
                break
            except Exception as e:
                last_exc = e
                continue

        if last_exc:
            raise last_exc
        raise ValueError("openai_no_response")

    def structured_parse(
        self,
        data,
        system_instructions="You are a helpful assistant designed to output JSON",
        output_model=None,
        model="default",
        store=False,
        max_retries=5,
    ):
        """
        Return a parsed Pydantic object using OpenAI Structured Outputs.

        `output_model` should be a Pydantic BaseModel class (e.g. ClassificationOutput).
        """
        messages = [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": data},
        ]

        if model == "default" or model is None:
            model = self.default_model

        if not self.model_supports_structured_outputs(model):
            raise ValueError("Configured Model does not support structured Outputs")

        last_exc = None
        for _ in range(int(max_retries or 1)):
            try:
                resp = self.client.beta.chat.completions.parse(
                    model=model,
                    response_format=output_model,
                    messages=messages,
                    store=store,
                )
                msg = resp.choices[0].message
                refusal = getattr(msg, "refusal", None)
                if refusal:
                    raise ValueError(f"openai_refusal:{refusal}")

                parsed = getattr(msg, "parsed", None)
                if parsed is not None:
                    return parsed

                # Fallback for SDK variants: validate from JSON content.
                content = getattr(msg, "content", None)
                if output_model is None:
                    return content
                obj = json.loads(content) if isinstance(content, str) else content
                return output_model.model_validate(obj)
            except Exception as e:
                last_exc = e
                continue

        if last_exc:
            raise last_exc
        raise ValueError("openai_no_response")

    def structured_response(self, data, system_instructions="You are a helpful assistant designed to output JSON", output_format=None, model="default", store=False, max_retries=5):

        messages = [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": data}
        ]

        try:
            if model == "default":
                model = self.default_model

            response = self.client.beta.chat.completions.parse(
                model=model,
                response_format=output_format,
                messages=messages,
                store=store

            )

            data = response.choices[0].message.content

            return data

        except Exception as e:
            print('Openai Configuration Missing')
            return e

    def tool_calling(self, instructions, prompt, tool_schemas, model=None):
        """

        :param instructions: Function instructions for the system
        :param prompt: User input
        :param tool_schemas: Schemas of the selectable tools
        :param model: GPT model to use
        :return:
        """

        if model is None:
            model = self.default_model

        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": instructions, },
                {"role": "user", "content": prompt}
            ],
            tools=tool_schemas,
        )

        return response.choices[0].message

    def image_reader(self, image_url, instruction, model=None):

        if model is None:
            model = self.default_model

        try:

            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": instruction},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url,
                                },
                            },
                        ],
                    }
                ],
                max_tokens=300,
            )

            return response.choices[0].message.content
        except Exception as e:
            print(e)
            return ""

    def summarize_chat(self, chat, prompt, json_output=True, model=None):

        if model is None:
            model = self.default_model

        max_retries = self.max_retries

        try:

            instructions = [{
                "role": "user",
                "content": f" {prompt} {json.dumps(chat)}"
            }]

            for _ in range(max_retries):

                try:

                    if json_output:
                        completion = self.client.chat.completions.create(
                            model=model,
                            response_format={"type": "json_object"},
                            messages=instructions
                        )
                    else:
                        completion = self.client.chat.completions.create(
                            model=model,
                            messages=instructions
                        )

                    return completion.choices[0].message.content

                except Exception as e:
                    return e

            else:
                print("Max retries exceeded.")

        except Exception as e:
            print('Openai Configuration Missing')


def get_simple_response(prompt, openai_api_key, model="gpt-4-turbo-preview", max_retries=5):

    try:

        client = OpenAI(api_key=openai_api_key)

        messages = [{"role": "user", "content": prompt}]

        for _ in range(max_retries):

            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages
                )

                return completion.choices[0].message.content

            except Exception as e:
                print(e)
                return e

        else:
            raise ValueError("Max retries exceeded")

    except Exception as e:
        return e


def get_json_response(data, openai_api_key, model="gpt-4-turbo-preview", system_instructions="You are a helpful assistant designed to output JSON", max_retries=5):

    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": data}
    ]

    try:

        client = OpenAI(api_key=openai_api_key)

        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=messages
        )

        data = response.choices[0].message.content

        return data

    except Exception as e:
        print('Openai Configuration Missing')
        return e


def summarize_chat(chat, prompt, openai_api_key, json_output=True, model="gpt-4-turbo-preview", max_retries=5):

    try:

        client = OpenAI(api_key=openai_api_key)

        instructions = [{
            "role": "user",
            "content": f" {prompt} {json.dumps(chat)}"
        }]

        for _ in range(max_retries):

            try:

                if json_output:
                    completion = client.chat.completions.create(
                        model=model,
                        response_format={"type": "json_object"},
                        messages=instructions
                    )
                else:
                    completion = client.chat.completions.create(
                        model=model,
                        messages=instructions
                    )

                return completion.choices[0].message.content

            except Exception as e:
                return e

        else:
            print("Max retries exceeded.")

    except Exception as e:
        print('Openai Configuration Missing')


def get_json_summary(chat, prompt, openai_api_key, model="gpt-4-turbo-preview"):

    try:

        client = OpenAI(api_key=openai_api_key)

        messages = [
            {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
            {"role": "user", "content": f" {prompt} {json.dumps(chat)}"},

        ]

        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=messages
        )

        summary = response.choices[0].message.content
        print(summary)
        return summary

    except Exception as e:
        print('Openai Configuration Missing')
        return e


def prompt_generator(prompt, summary, openai_api_key, model="gpt-4-turbo-preview", max_retries=5):
    try:

        client = OpenAI(api_key=openai_api_key)

        instructions = [{
            "role": "user",
            "content": f" {prompt} : {summary}"
        }]

        for _ in range(max_retries):

            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=instructions
                )
                return completion.choices[0].message.content

            except Exception as e:
                return e

        else:
            print("Max retries exceeded.")

    except Exception as e:
        print('Openai Configuration Missing')


def full_chat_reply(chat, openai_api_key, model="gpt-4-turbo-preview"):

    try:

        client = OpenAI(api_key=openai_api_key)

        prompt = """Return a JSON object with the following fields as mandatory, add more if convenient to enrich the 
        results.
        conversation_ended: true if conversation has covered all established steps, 
        next_assistant_utterance: next thing to say to the user, 
        user_data: {full_name, phone, email, address, birthdate, etc}, 
        work_experience: [{job, company, time_on_the_job}], 
        education:[{complete with relevant fields}],
        context_summary: Provide a comprehensive overview of the key points and topics discussed in the chat transcript, make sure to track all conversation steps to end the conversation only after all steps have been covered.   
        tags: List of keywords or phrases extracted from the user's input for quick reference or categorization
        """

        instructions = {"role": "system", "content": prompt}
        chat.append(instructions)

        print("====================================")
        print(chat)
        print("====================================")

        response = client.chat.completions.create(

            model=model,
            response_format={"type": "json_object"},
            messages=chat,
            seed=10
        )

        reply = response.choices[0].message.content

        return reply

    except Exception as e:
        print(e)
        print('Openai Configuration Missing')
        return "Ocurrio un error"


def full_chat_reply_tools(chat, openai_api_key, model="gpt-4-turbo-preview"):
    try:
        client = OpenAI(api_key=openai_api_key)

        prompt = """Return a JSON object with the following fields as mandatory, add more if convenient to enrich the 
        results.
        conversation_ended: true if conversation has covered all established steps, 
        next_assistant_utterance: next thing to say to the user, 
        user_data: {full_name, phone, email, address, birthdate, etc}, 
        work_experience: [{job, company, time_on_the_job}], 
        education:[{complete with relevant fields}],
        context_summary: Provide a comprehensive overview of the key points and topics discussed in the chat transcript, make sure to track all conversation steps to end the conversation only after all steps have been covered.   
        tags: List of keywords or phrases extracted from the user's input for quick reference or categorization
        """

        instructions = {"role": "system", "content": prompt}
        chat.append(instructions)

        print("====================================")
        print(chat)
        print("====================================")

        response = client.chat.completions.create(

            model=model,
            response_format={"type": "json_object"},
            messages=chat,
            seed=10,
            tools=tools,
            tool_choice="auto"

        )
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        ##########
        if tool_calls:
            # Step 3: call the function
            # Note: the JSON response may not always be valid; be sure to handle errors
            available_functions = {
                "recommend_branch": recommend_branch,
            }  # only one function in this example, but you can have multiple
            chat.append(response_message)  # extend conversation with assistant's reply
            # Step 4: send the info for each function call and function response to the model
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_to_call = available_functions[function_name]
                function_args = json.loads(tool_call.function.arguments)
                function_response = function_to_call(
                    address=function_args.get("address")
                )
                chat.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    }
                )  # extend conversation with function response
            second_response = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=chat,
                seed=10
            )  # get a new response from the model where it can see the function response


        ###########
            reply = second_response.choices[0].message.content
        else:

            reply = response.choices[0].message.content
        return reply

    except Exception as e:
        print(e)
        print('Openai Configuration Missing')
        return "Ocurrio un error"


def whisper_to_text(filepath: str, openai_api_key) -> str:

    try:

        client = OpenAI(api_key=openai_api_key)

        print(default_storage.url(filepath))
        with default_storage.open(filepath, "rb") as file:
            # Create a BytesIO object with the content of the MP3 file
            audio_file = BytesIO(file.read())
            audio_file.seek(0)
            audio_file.name = "speech.ogg"

        transcript = client.audio.transcriptions.create(file=audio_file, model="whisper-1")

        return transcript.text

    except Exception as e:
        print(e)
        print('Openai Configuration Missing')


def image_reader(image_url, instruction, openai_api_key, model="gpt-4-vision-preview"):
    try:
        client = OpenAI(api_key=openai_api_key)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                            },
                        },
                    ],
                }
            ],
            max_tokens=300,
        )

        return response.choices[0].message.content

    except Exception as e:
        print(e)
        return ""


def get_embedding(text, openai_api_key, model="text-embedding-3-small"):

    client = OpenAI(api_key=openai_api_key)

    try:
        response = client.embeddings.create(
            input=text,
            model=model
        )

        return response.data[0].embedding

    except Exception as e:
        print(e)
        return None


def image_reader_base64(base64_image, instruction, openai_api_key, model="gpt-4-vision-preview"):
    try:
        client = OpenAI(api_key=openai_api_key)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        },
                    ],
                }
            ],
            max_tokens=300,
        )

        return response.choices[0].message.content

    except Exception as e:
        print(e)
        return ""


def get_advanced_response(prompt:str, openai_api_key, response_format, model="gpt-4-turbo-preview", max_retries=5):
    try:
        client = OpenAI(api_key=openai_api_key)
        messages = [{"role": "user", "content": prompt}]

        for _ in range(max_retries):

            try:
                completion = client.beta.chat.completions.parse(
                    model=model,
                    messages=messages,
                    response_format=response_format,
                )
                return completion.choices[0].message.parsed

            except Exception as e:
                print(e)
                return e

        else:
            print("Max retries exceeded.")

    except Exception as e:
        print('Openai Configuration Missing')


def analyze_file(file, config: TenantConfiguration):

    base64_string = base64.b64encode(file.read()).decode("utf-8")

    if config.openai_integration_enabled:
        client = OpenAI(api_key=config.openai_api_key)
        response = client.responses.create(
            model="gpt-5",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": file.name,
                            "file_data": f"data:application/pdf;base64,{base64_string}",
                        },
                        {
                            "type": "input_text",
                            "text": "Analyze file contents and extract all data as a table, return a json object representing the file, add whatever entry needed to self document the structure",
                        },
                    ],
                },
            ]
        )

        print(response.output_text)
    else:
        raise Exception("Openai Configuration Disabled")
