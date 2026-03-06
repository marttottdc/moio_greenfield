from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from elevenlabs import ElevenLabs, play
ELEVEN_LABS_API_KEY = "b426ecbe23f865a839c80c517c830a9f"

# settings = VoiceSettings(speaking_rate=0.8)

client = ElevenLabs(
    api_key=ELEVEN_LABS_API_KEY,
)




# content_file = ContentFile(audio)

# created_file = default_storage.save("archivo.mp3", content_file)

# output = default_storage.url(created_file)
# print(output)

def text_to_speech(text, voice="JBFqnCBsd6RMkjVDRZzb", model="eleven_multilingual_v2"):

    speech = client.text_to_speech.convert(
        voice_id=voice,
        output_format="mp3_44100_128",
        text=text,
        model_id=model,
    )

    return speech


play(text_to_speech("hola amigos"))
