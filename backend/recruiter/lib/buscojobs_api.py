import re
from datetime import datetime

import fitz
import phonenumbers
from django.core.files.storage import default_storage


def valid_email(email):
    pattern = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    if re.match(pattern, email):
        return True
    else:
        return False


def valid_phone(phone):
    regions = ["UY", "AR", "CL", "BR", "MX"]

    print(phone)
    phone = phone.strip().replace(" ", "")

    if len(phone) > 15:
        if "-" in phone:
            phone = phone.split("-")[0]

        elif phone.startswith("+598"):
            phone = phone[:12]

        elif phone.startswith("0"):
            phone = phone[:9]

        elif phone.startswith("598"):
            phone = f"+{phone[:11]}"

        else:
            phone = phone[:8]

    for region in regions:
        try:
            parsed_phone_number = phonenumbers.parse(phone, region)
            if phonenumbers.is_valid_number(parsed_phone_number):

                return phonenumbers.format_number(parsed_phone_number, phonenumbers.PhoneNumberFormat.E164)
        except Exception as e:
            print(e)

    print("Teléfono no valido")
    return None


def phone_type(phone):
    parsed_phone_number = phonenumbers.parse(phone)
    return phonenumbers.number_type(parsed_phone_number)


def process_datos_personales(data_tuple):

    # Mandatory fields
    document_id = data_tuple[0].replace(".", "").replace("-", "")

    date_of_birth = data_tuple[1].split("-")[0].strip()
    parsed_date = datetime.strptime(date_of_birth, "%d/%m/%Y")
    date_of_birth = parsed_date.strftime("%Y-%m-%d")  # Format the parsed date into YYYY-MM-DD format

    # Detect if the fourth field is a postal code

    if len(data_tuple[2]) == 5:
        postal_code = data_tuple[2]
        # print(f' postal code {postal_code} found in index {2}')
        address_start_index = 3
    else:
        postal_code = ""
        address_start_index = 2

    email_index = 4

    while not valid_email(data_tuple[email_index]):
        email_index += 1
    email = data_tuple[email_index].lower()

    # print(f' email {email} found in index {email_index}')

    phone_index = email_index - 2
    whatsapp_index = phone_index + 1
    whatsapp_number = ""

    phone = valid_phone(data_tuple[phone_index])
    if phone:
        whatsapp_number = valid_phone(data_tuple[whatsapp_index])

    else:
        phone_index += 1
        phone = valid_phone(data_tuple[phone_index])

    if not whatsapp_number:
        if phone_type(phone) == 1:
            whatsapp_number = phone

    address_end_index = phone_index  # address end is detected by where phone index is found

    address = ' '.join(data_tuple[address_start_index:address_end_index]).replace("-", "").replace("  ", " ")

    return {
        "document": document_id,
        "date_of_birth": date_of_birth,
        "postal_code": postal_code,
        "address": address,
        "phone": phone,
        "whatsapp": whatsapp_number,
        "email": email
    }


def process_resumen(data_tuple):
    resumen = "".join(data_tuple)
    return resumen


def process_experiencia_laboral(data_tuple):
    """
    experiencia = []
    items = len(data_tuple)/8
    index = 0
    while index < items:
        item = {
            "desde": data_tuple[index + 0],
            "hasta": data_tuple[index + 1],
            "empresa": data_tuple[index + 2],
            "area": data_tuple[index + 3],
            "funcion": data_tuple[index + 4],
            "titulo": data_tuple[index + 5],
            "responsabilidades": data_tuple[index + 6],
            "detalle": data_tuple[index + 7]
        }
        experiencia.append(item)
        index += 1
    """
    experiencia = " ".join(data_tuple)
    return experiencia


def process_educacion(data):

    basic = data["Estudios Básicos"]
    advanced = data["Estudios Avanzados"]
    diplomas = data["Cursos / Certificaciones"]
    education ={
            "basic": " ".join(basic),
            "advanced": " ".join(advanced),
            "diplomas": " ".join(diplomas)
    }

    return education


def process_self_summary(data):
    summary = data["Resumen"]
    return "".join(summary)


def process_overall_knowledge(data):
    knowledge = data["Conocimientos"]
    return "".join(knowledge)


def ocr_buscojobs_cv_files(file_path):
    # Open the file using Django's default storage
    with default_storage.open(file_path, 'rb') as file:

        doc = fitz.open(stream=file.read(), filetype="pdf")  # Use the stream parameter to open the file-like object
        text = ""
        image_number = 0
        image_list = []

        for page in doc:
            text += page.get_text("text")
            image_list += page.get_images(full=True)

    # Define the section headers
    sections = ["Resumen", "Datos Personales", "Experiencia laboral", "Web & Redes", "Conocimientos", "Estudios Básicos", "Estudios Avanzados", "Cursos / Certificaciones", "Referencias", "Preferencias laborales"]
    extracted_data = {}

    # Split the text by lines
    lines = text.split('\n')

    # Assume first line is the name
    extracted_data["Nombre"] = lines[0]

    current_section = None
    for current_line in lines[1:]:  # Skip the name
        # Check if the line is a section header
        if current_line in sections:
            current_section = current_line
            extracted_data[current_section] = []

        elif current_section:
            extracted_data[current_section].append(current_line)

    for image_index, img in enumerate(image_list):
        xref = img[0]  # xref number
        if xref == 9:
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            # Save the image
            image_ext = base_image["ext"]
            image_filename = f"{lines[0].strip()}_{image_index + 1}.{image_ext}".replace(" ","_")
            image_number += 1

            extracted_data["image_bytes"] = image_bytes
            extracted_data["profile_pic"] = image_filename
            break

    doc.close()
    return extracted_data
