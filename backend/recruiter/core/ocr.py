
import base64
import os
from moio_platform.lib.openai_gpt_api import get_embedding, get_simple_response, image_reader_base64, get_advanced_response
# import fitz  # Requires system C++ libs - lazy load only when needed
# import pytesseract  # Requires system C++ libs - lazy load only when needed
from PIL import Image
import io
from django.core.files.storage import default_storage
from pydantic import BaseModel, ConfigDict
from portal.models import TenantConfiguration
import json

def extract_text_from_pdf(doc):
    text_from_img = ""
    text_from_text = ""

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text_from_text += page.get_text("text")
        pix = page.get_pixmap()
        img = Image.open(io.BytesIO(pix.tobytes()))
        text_from_img += pytesseract.image_to_string(img)

    return text_from_img, text_from_text


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def extract_images_from_pdf(doc, tenant_config: TenantConfiguration, image_target_instructions=""):
    if image_target_instructions == "":
        image_target_instructions = "es una imagen de una persona ? Potencialmente una imagen de perfil ? responde True o False"

    image_list = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        image_list += page.get_images(full=True)

    image_number = 0
    for image_index, img in enumerate(image_list):
        xref = img[0]  # xref number

        base_image = doc.extract_image(xref)
        image_bytes = base_image["image"]
        image_extension = base_image["ext"]  # Get the image extension (e.g., 'png', 'jpg')

        # Determine the MIME type based on the file extension
        mime_type = f"image/{image_extension}"

        # Encode the image to Base64 and prepend the MIME type

        encoded_image = base64.b64encode(image_bytes).decode("utf-8")
        respuesta = image_reader_base64(encoded_image, image_target_instructions,
                                        openai_api_key=tenant_config.openai_api_key,
                                        model=tenant_config.openai_default_model)

        if respuesta == "True":
            return f"data:{mime_type};base64,{encoded_image}"


def ocr_generic_pdf(config: TenantConfiguration, file_path="", file=None, ):
    print("Tratando de Leer el Archivo")

    if file_path == "" and file is None:
        raise ValueError("No file selected")

    if file_path != '':
        with default_storage.open(file_path, 'rb') as file:
            doc = fitz.open(stream=file.read(), filetype="pdf")
    elif file:
        doc = fitz.open(stream=file.read(), filetype="pdf")

    else:
        raise ValueError("No file selected")

    if doc:
        try:
            recognized_text = extract_text_from_pdf(doc)

            image_target_instructions = "es una imagen de una persona? Potencialmente una imagen de perfil? responde True o False"
            profile_pic = extract_images_from_pdf(doc, tenant_config=config,
                                                  image_target_instructions=image_target_instructions)
        except Exception as e:
            raise ValueError(e)

        finally:
            doc.close()

        formatting_instructions = """
                        "Formatea esto y clasifica la información de acuerdo a las siguientes categorías haciendo el mejor esfuerzo por completar todas las que sea posible: ["Resumen", "Nombre Completo","Telefono (solo dígitos)","Whatsapp (si esta vacio usar el telefono, sólo digitos)","Email(solo caracteres validos)","Fecha de nacimiento (YYYY-MM-DD)", "cedula (solo numeros)", "direccion", "Experiencia laboral", "Web & Redes", "Conocimientos",
                        "Estudios Básicos", "Estudios Avanzados", "Cursos / Certificaciones", "Referencias",
                        "Preferencias laborales"]" entregar un objeto json donde los criterios son una clave y el contenido es texto
                        """
        try:
            class CandidateData(BaseModel):
                name: str
                phone: str
                whatsapp: str
                email: str
                date_of_birth: str
                postal_code: str
                cedula: str
                address: str
                summary: str
                work_experience: list[str]
                education: list[str]
                skills: list[str]
                preferencias: list[str]

                model_config = ConfigDict(arbitrary_types_allowed=True)

        except Exception as e:
            raise ValueError(e)

        prompt = f' {formatting_instructions}:{recognized_text[0]} {recognized_text[1]}'

        info_candidato = get_advanced_response(prompt, openai_api_key=config.openai_api_key,
                                               model=config.openai_default_model, response_format=CandidateData)

        return info_candidato, profile_pic, doc



def image_ocr(filepath=""):

    # Carga la imagen
    image = Image.open(f'{filepath}.png')

    # Realiza OCR en la imagen, obteniendo un diccionario
    ocr_result = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

    # Convierte el diccionario a una cadena JSON
    json_str = json.dumps(ocr_result, ensure_ascii=False, indent=4)

    # Muestra la cadena JSON
    print(json_str)