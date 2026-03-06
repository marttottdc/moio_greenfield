import base64
import json
import os
import shutil

import fitz
import requests

URL = "https://webservices.psigmaonline.com"

"""
Código Mensaje
MSG0001 Solo se permiten peticiones por el método POST
MSG0002 No se encontraron datos de acceso en la petición
MSG0003 Datos de acceso no válido
MSG0004 La petición no tiene definida un código acción a realizar
MSG0005 La petición no se ha enviado con parámetros
MSG0006 Los parámetros deben venir en formato JSON
MSG0007 La acción enviada no es válida
MSG0008 Se debe enviar el campo "id_prueba" para esta acción
MSG0009 La petición no cuenta con el parámetro "token"
MSG0010 La petición no cuenta con un “token” válido
MSG0011 Se debe enviar el campo "id_perfil" para esta acción
MSG0012 Se debe enviar el campo "identificacion" para esta acción
MSG0013 Se debe enviar el campo "email" para esta acción
MSG0014 El valor "email" enviado no es un email válido
MSG0015 El valor "id_perfil" enviado no es válido o no corresponde a la prueba
MSG0016 El valor "id_prueba" enviado no es válido o no está activa para su uso
MSG0017 Se debe enviar el campo "id_programacion" para esta acción
MSG0018 El "id_programacion" enviado no es válido
MSG0019 No se pudo obtener el estado de unidades para la prueba solicitada
MSG0020 No se pudieron obtener resultados para la programación solicitada
MSG0021 No se pudieron obtener información para el perfil solicitado
MSG0022 No existe un baremo para la prueba solicitada, por favor comunicarse con Psigma
MSG0023 El usuarios autenticado no cuenta con un email válido, por favor edítelo para poder continuar
MSG0024 Se debe enviar el campo "fecha_inicio" para esta acción
MSG0025 Se debe enviar el campo "fecha_fin" para esta acción
MSG0026 No existe reporte para la prueba solicitada, por favor comunicarse con Psigma
MSG0027 Se presentó un error al realizar la programación, por favor comunicarse con Psigma
MSG0028 El campo "fecha_inicio" no es válida, el formato debe ser "dd-mm-yyyy"
MSG0029 El campo "fecha_fin" no es válida, el formato debe ser "dd-mm-yyyy"
MSG0030 No cuenta con unidades disponibles para realizar la programación
MSG0031 No se encontró ningún usuario con esa identificación
MSG0032 La programación debe estar en estado "procesado" para poder obtener resultados
MSG0033 Se requiere el parámetro "Content-Type" en el header del a petición
MSG0034 Aun no se ha registrado una url
MSG0035 Se debe enviar el campo "url" para esta acción
MSG0036 Ip no autorizada
"""


class PsigmaApi:

    def __init__(self, username, password, token):

        self.token = token
        credentials = f'{username}:{password}'
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        self.headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }

    def conn_test(self, id_prueba):

        payload = json.dumps({
            "token": self.token,
            "accion": 0,
            "parametros": {
                "id_prueba": id_prueba
            }
        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        return response.json()

    def get_available_examinations(self):

        payload = json.dumps({
            "token": self.token,
            "accion": 1,
            "parametros": {}
        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        return response.json()

    def get_available_profiles(self, id_prueba):

        payload = json.dumps({
            "token": self.token,
            "accion": 2,
            "parametros": {
                "id_prueba": id_prueba,
            }
        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        if response.status_code == 200:
            return response.json()
        else:
            return None

    def setup_examination(self, id_prueba, id_perfil, identificacion, email, fecha_inicio, fecha_fin, pro_grabar=False, enviar_mail=False):
        """

        :param id_prueba:
        :param id_perfil:
        :param identificacion:
        :param email:
        :param fecha_inicio: "30-08-2017"
        :param fecha_fin: "31-08-2017"
        :param pro_grabar:
        :param enviar_mail:
        :return:
        """

        payload = json.dumps({
            "token": self.token,
            "accion": 3,
            "parametros": {
                "id_prueba": id_prueba,
                "id_perfil": id_perfil,
                "identificacion": identificacion,
                "email": email,
                "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin,
                "pro_grabar": pro_grabar,
                "enviar_mail": enviar_mail

            }
        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        return response.json()

    def get_examination_status(self, id_programacion):
        payload = json.dumps({
            "token": self.token,
            "accion": 4,
            "parametros": {
                "id_programacion": id_programacion

            }
        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        return response.json()

    def get_available_units(self, id_prueba):
        payload = json.dumps({
            "token": self.token,
            "accion": 5,
            "parametros": {
                "id_prueba": id_prueba,

            }
        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        return response.json()

    def get_results(self, id_programacion):
        payload = json.dumps({
            "token": self.token,
            "accion": 6,
            "parametros": {
                "id_programacion": id_programacion,

            }
        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        return response.json()

    def get_profile_structure(self, id_perfil):
        payload = json.dumps({
            "token": self.token,
            "accion": 7,
            "parametros": {
                "id_perfil": id_perfil,

            }
        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        return response.json()

    def get_user_examinations(self, identificacion):
        payload = json.dumps({
            "token": self.token,
            "accion": 8,
            "parametros": {
                "identificacion": identificacion,

            }
        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        return response.json()

    def get_report_url(self, id_programacion):
        payload = json.dumps({
            "token": self.token,
            "accion": 9,
            "parametros": {
                "id_programacion": id_programacion,

            }
        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        return response.json()

    def setup_webhook_url(self, url):
        payload = json.dumps({
            "token": self.token,
            "accion": 10,
            "parametros": {
                "url": url,

            }
        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        return response.json()

    def get_url(self):
        payload = json.dumps({
            "token": self.token,
            "accion": 11,
            "parametros": {}

        })

        response = requests.request("POST", url=URL, headers=self.headers, data=payload)
        return response.json()



# ---------------------------- IMPORTACION DE EMAIL NO SOPORTADA OFICIALMENTE -------------------------

def import_psigma_data(file_path):
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text("text")
    doc.close()

    # Define the section headers
    sections = ["Resumen", "Datos Personales", "Experiencia laboral","Web & Redes", "Conocimientos", "Estudios Básicos", "Estudios Avanzados", "Cursos / Certificaciones", "Referencias", "Preferencias laborales"]
    extracted_data = {}

    # Split the text by lines
    lines = text.split('\n')
    #lines = text.split('info@psigmacorp.com')

    sections = ["RESUMEN"]
    extracted_data = {}

    # Split the text by lines
    # lines = text.split('\n')


    # Assume first line is the name
    # extracted_data["Nombre"] = lines[0]

    current_section = None
    for line in lines[1:]:  # Skip the name
        # Check if the line is a section header
        if line in sections:
            current_section = line
            extracted_data[current_section] = []
        elif current_section:
            extracted_data[current_section].append(line)


    return extracted_data


def extract_score(directory_path, target_subdirectory):
    # Ensure target subdirectory exists
    target_path = os.path.join(directory_path, target_subdirectory)
    if not os.path.exists(target_path):
        os.makedirs(target_path)

    # List and process all PDF files
    for filename in os.listdir(directory_path):
        if filename.endswith('.pdf'):
            file_path = os.path.join(directory_path, filename)
            # print(f"Processing {filename}...")
            # Example data extraction
            data = import_psigma_data(file_path)
            resumen = data["RESUMEN"]
            try:
                score_position = resumen.index("Potencial de Ajuste al perfil")-1
                score = resumen[score_position]
                cedula_position = resumen.index(" www.psigmacorp.com - info@psigmacorp.com")+2
                cedula = resumen[cedula_position].split(":")[1]

                result = {
                    "cedula": cedula,
                    "score": score
                }
                print(result)

            except ValueError:
                raise "Puntaje no encontrado"
            # Move file to subdirectory after processing
            shutil.move(file_path, os.path.join(target_path, filename))
            # print(f"Moved {filename} to {target_subdirectory}")

