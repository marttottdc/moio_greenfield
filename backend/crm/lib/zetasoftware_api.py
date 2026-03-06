import datetime
import json

import pandas as pd
import requests

#  Help:
#  https://ayuda.zetasoftware.com/apis/apis-rest

ZETA_SOFTWARE_BASE_URL = "https://api.zetasoftware.com/rest"

CFE_RECIBIDOS_DETALLE = "/APIs/RESTCFEsRecibidosV1CFERecibidoDetalle"
CFE_RECIBIDOS = "/APIs/RESTCFEsRecibidosV1CFEsRecibidos"

ARTICULOS_QUERY = "/APIs/RESTArticulosV3Query"
ARTICULOS_QUERY_V1 = "/APIs/RESTArticulosV1Query"
ARTICULOS_LOAD = "/APIs/RESTArticulosV3Load"
ARTICULOS_SAVE = "/APIs/RESTArticulosV3Save"
ARTICULOS_DELETE = "/APIs/RESTArticulosV3Delete"

CONTACTOS_SAVE = "/APIs/RESTContactosV3Save"
CONTACTOS_QUERY = "/APIs/RESTContactosV3Query"


CLIENTE_LOAD = "/APIs/RESTClienteV1Load"
CLIENTE_LOAD_V3 = "/APIs/RESTClienteV3Load"

FACTURA_CLIENTE_AGREGAR = "/APIs/RESTFacturaClienteV1Agregar"
FACTURA_PROVEEDOR_AGREGAR = "/APIs/RESTFacturaProveedorV1Agregar"

STOCK_ACTUAL_QUERY = "/APIs/RESTStockActualV3Query"
STOCK_ACTUAL_ARTICULO_QUERY = "/APIs/RESTStockActualArticuloV1Query"
STOCK_ACTUAL = "/APIs/RESTStockActualV3StockActualModificado"

PRECIOS_ARTICULO_PRECIO_VENTA = "/APIs/RESTPreciosArticulosV2ObtenerPrecioVenta"
PRECIOS_ARTICULO_PRECIO_VENTA_SAVE = "/APIs/RESTPreciosVentaV1Save"

VENTAS_DETALLADAS = "/APIs/RESTFacturaClienteV4VentasDetalladas"
VENTAS_DETALLE_FACTURA = "/APIs/RESTFacturaClienteV4VentaDetallada"
VENTAS_FACTURA_CLIENTE_QUERY = "/APIs/RESTFacturaClienteV2QueryVentas"
VENTAS_FACTURA_CLIENTE_QUERY_V4 = "APIs/RESTFacturaClienteV4QueryVentas"


class ZetaSoftwareAPI:

    def __init__(self, devCode, devKey, compayCode, companyKey, rolCodigo=1):
        """
        :param devCode:
        :param devKey:
        :param compayCode:
        :param companyKey:
        :param rolCodigo:
        """

        self.base_url = ZETA_SOFTWARE_BASE_URL

        self.connection = {
                        "DesarrolladorCodigo": devCode,
                        "DesarrolladorClave": devKey,
                        "EmpresaCodigo": compayCode,
                        "EmpresaClave": companyKey,
                        "RolCodigo": rolCodigo,
        }
        self.headers = {
            "Content-Type": "application/json"
        }
        self.products = None

    def get_products_by_name(self, name_contains: str = "", inactive: bool = False):
        # Fetch product data from ZetaSoftware
        # Configuración inicial
        endpoint = self.base_url + ARTICULOS_QUERY

        activos = "S"
        if inactive:
            activos = "N"

        page_number = 0
        product_list = []
        while True:
            payload = {
                "QueryIn": {
                    "Connection": self.connection,
                    "Data": {
                        "Page": page_number,
                        "Filters": {
                            "NombreContiene": name_contains,
                            "ArticulosActivo": activos
                        }
                    }
                }
            }

            response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))
            last_page = response.json()["QueryOut"]["IsLastPage"]
            if last_page:
                break

            page_number += 1

            if response.status_code == 200:
                # print("Operación exitosa")

                product_list.extend(response.json()["QueryOut"]["Response"])
                # return response.json()["QueryOut"]["Response"]
                # print(f"Product list len: {len(product_list)}")

            elif response.status_code == 404:
                print("No encontrado")
                # return None

            else:
                print(f"Error: {response.status_code}, {response.text}")
                # return None

        print(f"{len(product_list)} articulos encontrados")
        return product_list

        # Manejo de respuestas

    def get_products_by_barcode(self, barcode: str):
        # Fetch product data from ZetaSoftware
        # Configuración inicial
        endpoint = self.base_url + ARTICULOS_QUERY_V1
        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "QueryIn": {
                "Connection": self.connection,
                "Data": {
                    "Page": 0,
                    "Filters": {
                        "CodigoBarras": barcode

                    }
                }
            }
        }

        response = requests.post(endpoint, headers=headers, data=json.dumps(payload))

        # Manejo de respuestas
        if response.status_code == 200:
            print("Operación exitosa")
            print(json.dumps(response.json(), indent=4))
        elif response.status_code == 404:
            print("No encontrado")
        else:
            print(f"Error: {response.status_code}, {response.text}")

    def load_product(self, sku):

        endpoint = self.base_url + ARTICULOS_LOAD

        payload = {
            "LoadIn": {
                "Connection": self.connection,
                "Codigo": sku
            }
        }

        return requests.post(endpoint, headers=self.headers, data=json.dumps(payload)).json()["LoadOut"]["Response"]

    def create_or_update_customer(self, customer):

        endpoint = self.base_url + CONTACTOS_SAVE
        # Create a customer in ZetaSoftware
        payload = {
            "SaveIn": {
                "Connection": self.connection,
                "Data":  customer

            }
        }

        response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))
        return response.json()

    def get_customers(self):

        endpoint = self.base_url + CLIENTE_LOAD

        payload = {
            "LoadIn": {
                "Connection": self.connection,
                "Codigo": "1"
            }
        }

        response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))

        # Manejo de respuestas
        if response.status_code == 200:
            print("Operación exitosa")
            print(json.dumps(response.json(), indent=4))

        elif response.status_code == 404:
            print("No encontrado")

        else:
            print(f"Error: {response.status_code}, {response.text}")

    def get_customer_type(self, codigo):

        endpoint = self.base_url + CLIENTE_LOAD_V3

        payload = {
            "LoadIn": {
                "Connection": self.connection,
                "Codigo": codigo
            }
        }

        response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))

        # Manejo de respuestas
        if response.status_code == 200:
            return response.json()["LoadOut"]["Response"]["CategoriaCodigo"]

        elif response.status_code == 404:
            print("No encontrado")

        else:
            print(f"Error: {response.status_code}, {response.text}")

    def create_order(self, order):
        endpoint = self.base_url + FACTURA_CLIENTE_AGREGAR

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

        payload = {
                "AgregarIn": {
                    "Connection": self.connection,
                    "Data": order
                }
        }

        response = requests.post(endpoint, headers=headers, data=json.dumps(payload))
        return bool(response.json()["AgregarOut"]["Succeed"])

    def delete_product(self, code: str):

        endpoint = self.base_url + ARTICULOS_DELETE

        payload = {
            "DeleteIn": {
                "Connection": self.connection,
                "Codigo": code
            }
        }

        response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))

        # Manejo de respuestas
        if response.status_code == 200:
            print(f"Borrado exitoso: {code}")

        elif response.status_code == 404:
            print("No encontrado")
        else:
            print(f"Error: {response.status_code}, {response.text}")

    def get_product_stock(self, sku: str, deposito=1, local=1):

        enpoint = self.base_url + STOCK_ACTUAL_ARTICULO_QUERY

        payload = {
                "QueryIn": {
                    "Connection": self.connection,
                    "Data": {
                        "Page": "0",
                        "Filters": {
                                "ArticuloCodigo": sku,
                                "DepositoCodigo": deposito,
                                "LocalCodigo": local,

                            }
                    }
                }
        }
        response = requests.post(enpoint, headers=self.headers, data=json.dumps(payload))

        # Manejo de respuestas
        if response.status_code == 200:
            # print("Consulta Stock exitosa")
            # print (response.content)
            if len(response.json()["QueryOut"]["Response"]) > 0:
                return response.json()["QueryOut"]["Response"][0]["StockActual"]
            else:
                return 0
            # print(response.json()["Response"])

        else:
            print(f"Error: {response.status_code}, {response.text}")
            return None

    def get_product_price(self, sku: str, precio_venta=1):

        endpoint = self.base_url + PRECIOS_ARTICULO_PRECIO_VENTA

        payload = {
            "ObtenerPrecioVentaIn": {
                "Connection": self.connection,
                "Data": {
                    "ArticuloCodigo": sku,
                    "PrecioVentaCodigo": precio_venta,
                    }
                }
            }

        response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))

        if response.status_code == 200:

            return response.json()["ObtenerPrecioVentaOut"]["Response"]

        else:
            print(f"Error: {response.status_code}, {response.text}")
            return None

    def set_product_price(self, sku: str, lista: str):
        # TODO: no implementado

        endpoint = self.base_url + PRECIOS_ARTICULO_PRECIO_VENTA_SAVE

        payload = {
            "SaveIn": {
                "Connection": self.connection,
                "Data": {
                    "Codigo": "<integer>",
                    "Nombre": "<string>",
                    "Abreviacion": "<string>",
                    "Porcentaje": "<double>",
                    "PrecioBaseCodigo": "<string>",
                    "SumarUtilidadArticulo": "<string>",
                    "VigenciaHasta": "<date>"
                }
            }
        }

    def product_update(self, product):

        endpoint = self.base_url + ARTICULOS_SAVE

        payload = {
            "SaveIn": {
                "Connection": self.connection,
                "Data": product
            }
        }

        response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))

        if response.status_code == 200:
            current_time = datetime.datetime.now()
            print(f'{current_time} - Producto {product["Codigo"]} actualiazdo exitosamente')

        else:
            print(f"Error: {response.status_code}, {response.text}")

    def get_products(self, refresh=False):
        # TODO: No implementado

        if self.products is None or refresh:

            self.products = self.get_products_by_name()

        return self.products

    def list_contacts(self):
        endpoint = self.base_url + CONTACTOS_QUERY

        page = 0
        clients = []
        while True:
            payload = {
                        "QueryIn": {
                            "Connection": self.connection,
                            "Data": {
                                "Page": page,
                                "Filters": {

                                }
                            }
                        }
                    }

            response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))
            clients.extend(response.json()["QueryOut"]["Response"])

            if response.json()["QueryOut"]["IsLastPage"]:
                break
            else:
                page += 1

        return clients

    def get_customercode(self, email):

        clientes = self.list_contacts()
        df = pd.DataFrame(clientes)

        result = df[df['Email1'].str.contains(email, case=False, na=False)]
        result_list = result.to_dict('records')

        if len(result_list) > 0:
            return result_list[0]['Codigo']
        else:
            return None

    def get_next_code(self):

        clientes = self.list_contacts()
        df = pd.DataFrame(clientes)
        result_list = df.to_dict('records')

        code = df['Codigo'].max()
        return str(int(code)+1)

    def get_sales_details(self, anio, mes, moneda):

        endpoint = self.base_url + VENTAS_DETALLADAS

        payload = {
            "VentasDetalladasIn": {
                "Connection": self.connection,
                "Data": {
                    "Mes": mes,
                    "Anio": anio,
                    "Moneda": moneda
                }
            }
        }

        response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))
        return response.json()["VentasDetalladasOut"]["Response"]["VentasDetalladas"]

    def invoice_details(self, number):
        enpoint = self.base_url + VENTAS_DETALLE_FACTURA

        payload = {
            "VentaDetalladaIn": {
                "Connection": self.connection,
                "Data": {
                    "FacturaId": number
                }
            }
        }
        response = requests.post(enpoint, headers=self.headers, data=json.dumps(payload))
        # print(response.json())

        if response.status_code == 200:
            response = response.json()
            if response["VentaDetalladaOut"]["Succeed"]:
                return response["VentaDetalladaOut"]["Response"]["VentasDetalladas"]
            else:
                print(response["VentaDetalladaOut"]["Response"]["Mensaje"])

        return []

    def get_sales(self, month, year, desde, hasta):

        endpoint = self.base_url + VENTAS_FACTURA_CLIENTE_QUERY

        page = 0
        last_page = False
        full_sales = []
        while not last_page:

            payload = {
                "QueryVentasIn": {
                    "Connection": self.connection,
                    "Data": {
                        "Page": page,
                        "Filters": {
                            "MonedaCodigo": 1,
                            "Mes": month,
                            "Anio": year,
                            "FechaDesde": desde,
                            "FechaHasta": hasta


                        }
                    }
                }
            }
            response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))
            # Manejo de respuestas
            if response.status_code == 200:

                last_page = response.json()["QueryVentasOut"]['IsLastPage']
                full_sales.extend(response.json()["QueryVentasOut"]["Response"])
                page += 1

            elif response.status_code == 404:
                print("Sin ventas")
                return None

            else:
                print(f"Error: {response.status_code}, {response.text}")
                return None

        return full_sales

    def get_sales_v4(self, desde, hasta):

        endpoint = self.base_url + VENTAS_FACTURA_CLIENTE_QUERY_V4

        page = 0
        last_page = False
        full_sales = []
        while not last_page:

            payload = {
                "QueryVentasIn": {
                    "Connection": self.connection,
                    "Data": {
                        "Page": page,
                        "Filters": {
                            "MonedaCodigo": 1,
                            "Mes": 11,
                            "Anio": 2023,
                            "FechaDesde": desde,
                            "FechaHasta": hasta


                        }
                    }
                }
            }

            response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))
            # Manejo de respuestas
            if response.status_code == 200:

                last_page = response.json()["QueryVentasOut"]['IsLastPage']
                full_sales.extend(response.json()["QueryVentasOut"]["Response"])
                page += 1

            elif response.status_code == 404:
                print("Sin ventas")
                return None

            else:
                print(f"Error: {response.status_code}, {response.text}")
                return None

        return full_sales

    def get_stock(self, deposito, local):

        endpoint = self.base_url + STOCK_ACTUAL_QUERY

        page = 0
        last_page = False
        full_stock = []
        while not last_page:
            payload = {
                    "QueryIn": {
                        "Connection": self.connection,
                        "Data": {
                            "Page": str(page),
                            "Filters": {
                                "CantidadDesde": "0",
                                "DepositoCodigo": str(deposito),
                                "LocalCodigo": str(local),

                            }
                        }
                    }
                }

            response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))
            # Manejo de respuestas
            if response.status_code == 200:

                last_page = response.json()["QueryOut"]['IsLastPage']
                full_stock.extend(response.json()["QueryOut"]["Response"])
                page += 1

            elif response.status_code == 404:
                print("Stock no encontrado")
                return None

            else:
                print(f"Error: {response.status_code}, {response.text}")
                return None

        return full_stock

    def get_received_invoices(self, desde, hasta, pagina=1):

        endpoint = self.base_url + CFE_RECIBIDOS

        payload = {
          "CFEsRecibidosIn": {
            "Connection": self.connection,
            "Data": {
              # "LocalCodigo": "<integer>",
              "FechaDesde": desde,
              "FechaHasta": hasta,
              # "TipoCFECodigo": "<integer>",
              "Pagina": pagina
            }
          }
        }

        response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))

        if response.status_code == 200:
            response = response.json()

            if response["CFEsRecibidosOut"]["Succeed"]:
                document_list = response["CFEsRecibidosOut"]["Response"]["ListaCFEs"]
                return document_list
            else:
                print(response["Mensaje"])
                return None

        else:
            return None

    def load_received_cfe_details(self, rut_emisor="", tipo_cfe="", serie_cfe="", numero_cfe=None):

        endpoint = self.base_url + CFE_RECIBIDOS_DETALLE

        payload = {
              "CFERecibidoDetalleIn": {
                "Connection": self.connection,
                "Data": {
                  "EmisorRUT": rut_emisor,
                  "CFETipo": tipo_cfe,
                  "CFESerie": serie_cfe,
                  "CFENumero": numero_cfe
                }
              }
            }

        response = requests.post(endpoint, headers=self.headers, data=json.dumps(payload))

        if response.status_code == 200:
            response = response.json()

            if response["CFERecibidoDetalleOut"]["Succeed"]:
                document_list = response["CFERecibidoDetalleOut"]["Response"]["CFEDetalle"]
                return document_list

            else:
                print(response["Mensaje"])
                return None

        else:
            return None

    def get_sku_stock(self, sku):
        pass

