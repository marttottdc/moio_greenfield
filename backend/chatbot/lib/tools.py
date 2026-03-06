import json
# from io import BytesIO


from PIL import Image
# from django.core.files.storage import default_storage
# from pydub import AudioSegment


# def convert_ogg_to_mp3(filename_ogg_file) -> str:
#
#     with default_storage.open(filename_ogg_file, "rb") as file:
#         # Create a BytesIO object with the content of the MP3 file
#         buffer_in = BytesIO(file.read())
#
#     # buffer_in.seek(0)
#
#     if len(buffer_in.getvalue()) > 0:
#         try:
#
#             buffer_in.seek(0)
#             ogg_audio = AudioSegment.from_ogg(buffer_in)   # Load the audio data from the buffer
#
#             buffer_out = BytesIO()  # Create a BytesIO buffer to hold the audio data
#             ogg_audio.export(out_f=buffer_out, format="mp3")  # Export the audio to the buffer in MP3 format
#             buffer_out.seek(0)  # Seek back to the beginning of the buffer
#
#             # Save it to S3
#             # Change file_name extension
#             mp3_file_name = filename_ogg_file.replace("ogg", "mp3")
#             filename = default_storage.save(mp3_file_name, buffer_out)  # Save the buffer to Django storage (S3)
#
#             return filename
#
#         except Exception as e:
#             print(f"Error decoding audio data: {str(e)}")
#             return None
#
#
#     else:
#         print('Buffer empty')
#         return None

