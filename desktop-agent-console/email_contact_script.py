import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os

# Cargar variables de entorno
load_dotenv()

SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')

# Leer Excel
file_path = input('Ruta del archivo Excel con clientes: ')
df = pd.read_excel(file_path)

# Pedir mensaje
print('Escribe el mensaje (usa {nombre} para insertar el nombre del cliente):')
mensaje_template = []
while True:
    linea = input()
    if linea == '':
        break
    mensaje_template.append(linea)
mensaje_template = '\n'.join(mensaje_template)

# Configurar servidor SMTP
def enviar_email(destino, nombre, mensaje):
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = destino
    msg['Subject'] = 'Mensaje personalizado'

    cuerpo = mensaje.format(nombre=nombre)
    msg.attach(MIMEText(cuerpo, 'plain'))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

# Enviar emails
for idx, row in df.iterrows():
    nombre = row['nombre']
    email = row['mail']
    mensaje = mensaje_template
    try:
        enviar_email(email, nombre, mensaje)
        print(f'Email enviado a {nombre} <{email}>')
    except Exception as e:
        print(f'Error enviando a {nombre} <{email}>: {e}')

print('Proceso terminado.')
