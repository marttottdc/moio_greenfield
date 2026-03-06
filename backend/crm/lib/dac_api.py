
import base64
import json

import requests


def stream_byte_to_pdf(base64_data, name):
    # Decode the Base64-encoded data into a byte array
    byte_data = base64.b64decode(base64_data)

    # Specify the desired filename for the output PDF file
    filename = f"{name}.pdf"

    # Open a file in write binary mode and write the byte data to it
    with open(filename, "wb") as fs:
        fs.write(byte_data)



class DacApi:

    def __init__(self, url, user, password):

        self.base_url = url
        self.user = user
        self.password = password

        body = {
            "Login": self.user,
            "Contrasenia": self.password
        }

        endpoint = self.base_url+"/wsLogin"
        response = requests.post(endpoint, data=body).json()
        if response["result"] == 0:
            self.session_id = response["data"][0]["ID_Session"]
        else:
            raise ValueError(response["data"])

    def end_session(self):
        endpoint = self.base_url+"/wsLogOut"

        body = {
            "ID_Sesion": self.session_id
        }

        result = requests.post(endpoint, body).json()
        print(result)

    def get_barrio(self, barrio: str):
        """

        :param barrio:
        :return:
        """

        endpoint = "/wsBarrio"
        params = {
            "ID_Sesion": self.session_id,
            "Barrrio": barrio,

        }
        response = requests.get(self.base_url+endpoint, params=params)
        # response = requests.get(url + endpoint, params=params)

        if response.status_code == 200:
            return response.json()["data"]

        else:
            return None

    def rastrear(self, rastreo="", pedido=""):
        """
        :param pedido:
        :param rastreo:
        :return:
        """

        endpoint = "/wsRastreoGuia"

        if rastreo != "":

            oficina_origen = rastreo[:3]
            guia = rastreo[3:]

        else:
            oficina_origen = ""
            guia = ""

        body = {
            "K_Oficina_Origen": oficina_origen,
            "K_Guia": guia,
            "Referencia": pedido,
            "ID_Sesion": self.session_id
        }

        response = requests.post(self.base_url + endpoint, data=body)
        if response.status_code == 200:
            data = response.json()
            if data["result"] == 0:
                return data["data"], data["dataHistoria"]
            else:
                print(data["data"])
                return None
        else:
            print(response.text)
            return None

    def mis_guias(self,fecha_inicio, fecha_fin, rut, tipo_busqueda=1):
        """

        :param fecha_inicio:
        :param fecha_fin:
        :param rut:
        :param tipo_busqueda:
        :return:
        """
        endpoint = "/wsObtieneGuiasCliente"  # http://altis-web.grupoagencia.com:8087/JAgencia.asmx/wsObtieneGuiasCliente

        body = {
            "K_Cliente": self.user,
            "Busqueda": tipo_busqueda,
            "FI": fecha_inicio,
            "FF": fecha_fin,
            "RUT": rut,
            "ID_Sesion": self.session_id
        }
        response = requests.post(self.base_url+endpoint, data=body).json()

        if response["result"] == 0:
            return response["data"]
        else:
            print(response["data"])
            return []

    def get_tipos_envio(self):
        endpoint = "/wsTipodeEntrega"
        body = {
            "K_Tipo_Entrega": 0,
            "ID_Sesion": self.session_id

        }
        response = requests.post(url = self.base_url+endpoint, data=body).json()
        print(response)

    def get_tipos_guia(self):
        endpoint = "/wsTipodeGuia"
        body = {
            "K_Tipo_Guia": 0,
            "ID_Sesion": self.session_id

        }
        response = requests.post(url = self.base_url+endpoint, data=body).json()
        print(response)

    def get_costo(self):
        """
        http://altis-web.grupoagencia.com:8087/JAgencia.asmx/wsObtieneCosto
        :return:
        """
        endpoint = "/wsObtieneCosto"

        body = {
                "ID_Sesion": self.session_id,
                "K_Cliente_Remitente": 1,
                "K_Cliente_Destinatario": 5,
                "K_Barrio": 300,
                "K_Ciudad_Destinatario": 185,
                "K_Estado_Destinatario": 10,
                "K_Pais_Destinatario": 1,
                "CP_Destinatario": 11000,
                "K_Oficina_Destino": 601, "Entrega": 1,
                "Paquetes_Ampara": 4,
                "Chicos": 2,
                "Medianos": 1,
                "Grandes": 1,
                "Extragrande": 0,
                "Cartas": 0,
                "Sobres": 0,
                "K_Articulo": 0,
                "K_Tipo_Guia": 2,
                "CostoMercaderia": "",
                "esRecoleccion": 0

        }
        print ("Pending implementation")

    def new_delivery(self, fecha_levante, nombre_rte, telefono_rte, codigo_dom_recoleccion, nombre_dest, domicilio_dest, documento_dest="", telefono_dest="", notas="", ref_pedido="",  costo_mercaderia="", tipo_guia="4", tipo_entrega="2", tipo_envio="1", lat_dest="", long_dest=""):
        """

        :param fecha_levante:
        :param nombre_rte:
        :param telefono_rte:
        :param codigo_dom_recoleccion:
        :param nombre_dest:
        :param domicilio_dest:
        :param documento_dest:
        :param telefono_dest:
        :param notas:
        :param ref_pedido:
        :param costo_mercaderia:
        :param tipo_guia:
        :param tipo_entrega:
        :param tipo_envio:
        :param lat_dest:
        :param long_dest:
        :return:
        """
        endpoint = "/wsInGuia_Levante"
        detalle_paquetes = json.dumps([{"Cantidad": "1", "Tipo": "1"}])

        body = {
            "ID_Sesion": self.session_id,
            "K_Tipo_Guia": tipo_guia,
            "K_Tipo_Envio": tipo_envio,
            "Entrega": tipo_entrega,
            "K_Domicilio_recoleccion": codigo_dom_recoleccion,
            "F_Recoleccion": fecha_levante,
            "Telefono_Remitente": telefono_rte,
            "D_Cliente_Remitente": nombre_rte,
            "K_Cliente_Destinatario": 5,
            "Cliente_Destinatario": nombre_dest,
            "Direccion_Destinatario": domicilio_dest,
            "Telefono": telefono_dest,
            "RUT": documento_dest,
            "Observaciones": notas,
            "Paquetes_Ampara": 1,
            "Detalle_Paquetes": detalle_paquetes,
            "CostoMercaderia": costo_mercaderia,
            "Referencia_Pago": "",
            "CodigoPedido": ref_pedido,
            "Serv_DDF": "",
            "Serv_Cita": "",
            "K_Oficina_Destino": "",
            "Latitud_Destino": lat_dest,
            "Longitud_Destino": long_dest
        }

        response = requests.post(self.base_url+endpoint, data=body)

        if response.status_code == 200:
            response_data = response.json()
            if response_data["result"] == 0:
                return response_data["data"]
            else:
                raise ValueError(response_data["data"])
        else:
            raise ValueError(f'Error {response.status_code}')

    def get_label(self, rastreo):

        oficina = rastreo[:3]
        guia = rastreo[3:]
        endpoint = "/wsGetPegote"
        body = {
            "K_Oficina": oficina,
            "K_Guia": guia,
            "CodigoPedido": "",
            "ID_Sesion":self.session_id
        }

        response = requests.post(self.base_url+endpoint, data=body).json()

        stream_byte_to_pdf(response["data"]["Pegote"], "labels/"+rastreo)

    def get_pickup_addresses(self):
        endpoint = "/wsDomRecoleccion"
        body = {
            "ID_Sesion": self.session_id
        }
        response = requests.post(self.base_url+endpoint, data=body).json()
        print(response)

    def cancel_delivery(self, guia, oficina):
        endpoint = "/wsCancelaGuia"
        oficina = oficina
        guia = guia

        body = {
            "K_Oficina": oficina,
            "K_Guia":guia,
            "ID_Sesion": self.session_id
        }

        response = requests.post(self.base_url+endpoint, data=body).json()
        print(response)

    def get_cupos_flex(self, fecha):

        endpoint = "/wsCuposDisponibles"

        body ={
            "ID_Sesion": self.session_id,
            "Fecha_Consulta": fecha
        }

        response = requests.post(self.base_url+endpoint, data= body).json()
        return response

    def cobertura_flex(self, direccion, ciudad, lat="", long=""):
        endpoint = "/wsDomicilioFlex"
        body ={
            "ID_Sesion": self.session_id,
            "Direccion": direccion,
            "Ciudad": ciudad,
            "Latitud": lat,
            "Longitud": long
        }
        response = requests.post(self.base_url+endpoint, data=body).json()
        print(response)

    def new_delivery_flex(self):
        print("Flex Delivery Not implemented")
        endpoint ="/wsInGuiaFlex"
        body ={

        }