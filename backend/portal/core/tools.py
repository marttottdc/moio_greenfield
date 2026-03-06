import secrets
from io import BytesIO
import qrcode
from django.core.files import File

from portal.config import get_portal_configuration


def generate_qr_code(type_qr: str, data: str):

    if type_qr == 'asset':
        url = get_portal_configuration().my_url + 'fam/asset_details/' + data

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )

    qr.add_data(url)

    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # you can modify the filename as per your requirements.
    file_obj = BytesIO()
    img.save(file_obj, 'PNG')
    file_obj.seek(0)

    return File(file_obj, name=f"qr_code_{data}.png")


def generate_cookie_value(length=16):
    # Generate a random string of specified length
    # random_bytes = secrets.token_bytes(length)
    random_value = secrets.token_hex(length)

    return random_value


def print_nested_json(data, indent=0):
    if isinstance(data, dict):
        for key, value in data.items():
            print(' ' * indent + str(key))
            print_nested_json(value, indent + 4)
    elif isinstance(data, list):
        for item in data:
            print_nested_json(item, indent + 4)
    else:
        print(' ' * indent + str(data))


def infer_schema(data):
    schema = {}
    if isinstance(data, dict):
        for key, value in data.items():
            schema[key] = infer_schema(value)
    elif isinstance(data, list):
        if data and all(isinstance(item, dict) for item in data):
            schema = infer_schema(data[0])  # Assuming all items have the same schema
        else:
            schema = "array"
    else:
        schema = type(data).__name__

    return schema