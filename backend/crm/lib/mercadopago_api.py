import requests
from mercadopago import sdk
MP_ACCESS_TOKEN = "TEST-2643229155743999-062610-ea525679bf04bbfd46d1f44e713a6c02-2312437806"
MP_PUBLIC_KEY = "TEST-a812607c-8148-4ff6-8bf4-b11167757695"


def create_suscription_plan():

    url ="https://api.mercadopago.com/preapproval_plan"

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "reason": "Yoga classes",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "repetitions": 12,
            "billing_day": 10,
            "billing_day_proportional": True,
            "free_trial": {
                "frequency": 1,
                "frequency_type": "months"
            },
            "transaction_amount": 400,
            "currency_id": "UYU"
        },
        "payment_methods_allowed": {
            "payment_types": [
                {}
            ],
            "payment_methods": [
                {}
            ]
        },
    "back_url": "https://www.yoursite.com"
    }
    response = requests.post(url, headers=headers, json=payload)

    print(response.text)
    """RESPONSE SAMPLE
        {
      "id": "2c938084726fca480172750000000000",
      "application_id": 1234567812345678,
      "collector_id": 100200300,
      "reason": "Yoga classes",
      "auto_recurring": {
        "frequency": 1,
        "frequency_type": "months",
        "repetitions": 12,
        "billing_day": 10,
        "billing_day_proportional": true,
        "free_trial": {
          "frequency": 1,
          "frequency_type": "months"
        },
        "transaction_amount": 10,
        "currency_id": "ARS"
      },
      "payment_methods_allowed": {
        "payment_types": [
          {}
        ],
        "payment_methods": [
          {}
        ]
      },
      "back_url": "https://www.mercadopago.com.ar",
      "external_reference": 23546246234,
      "init_point": "https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_plan_id=2c938084726fca480172750000000000",
      "date_created": "2022-01-01T15:12:25.892Z",
      "last_modified": "2022-01-01T15:12:25.892Z",
      "status": "active"
    }
    
    """

def create_subscription(preapproval_plan_id):

    url ="https://api.mercadopago.com/preapproval"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "preapproval_plan_id": preapproval_plan_id,
        "reason": "Yoga classes",
        "external_reference": "YG-1234",
        "payer_email": "test_user@testuser.com",
        "card_token_id": "e3ed6f098462036dd2cbabe314b9de2a",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "start_date": "2020-06-02T13:07:14.260Z",
            "end_date": "2022-07-20T15:59:52.581Z",
            "transaction_amount": 10,
            "currency_id": "ARS"
        },
        "back_url": "https://developer.moio.ai/successful_subscription",
        "status": "authorized"
    }
    response = requests.post(url, headers=headers, json=payload)
    print(response.text)
    """RESPONSE SAMPLE
        {
      "id": "2c938084726fca480172750000000000",
      "version": 0,
      "application_id": 1234567812345678,
      "collector_id": 100200300,
      "preapproval_plan_id": "2c938084726fca480172750000000000",
      "reason": "Yoga classes.",
      "external_reference": 23546246234,
      "back_url": "https://www.mercadopago.com.ar",
      "init_point": "https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_id=2c938084726fca480172750000000000",
      "auto_recurring": {
        "frequency": 1,
        "frequency_type": "months",
        "start_date": "2020-06-02T13:07:14.260Z",
        "end_date": "2022-07-20T15:59:52.581Z",
        "currency_id": "ARS",
        "transaction_amount": 10,
        "free_trial": {
          "frequency": 1,
          "frequency_type": "months"
        }
      },
      "payer_id": 123123123,
      "card_id": 123123123,
      "payment_method_id": 123123123,
      "next_payment_date": "2022-01-01T11:12:25.892-04:00",
      "date_created": "2022-01-01T11:12:25.892-04:00",
      "last_modified": "2022-01-01T11:12:25.892-04:00",
      "status": "pending"
    }
    """

def subscription_plan_update(preapproval_plan_id):
    """
        Modificar monto	Permite modificar el monto de una suscripción existente. Envía el nuevo monto a través de auto_recurring.transaction_amount y auto_recurring.currency_id en un PUT al endpoint /preapproval/{id}.
        Modificar tarjeta del medio de pago principal	Permite modificar la tarjeta asociada a la suscripción existente. Envía un PUT con el nuevo token en atributo card_token_id para el endpoint /preapproval/{id}.
        Modificar medio de pago secundario	Permite agregar un segundo medio de pago a una suscripción existente. Envía un PUT en el endpoint /preapproval/{id} con los parámetros card_token_id_secondary y payment_method_id_secondary en caso de que el método secundario sea una tarjeta, y sólo payment_method_id_secondary para otros medios de pago.
        Cancelar o pausar suscripción	Permite cancelar o pausar una suscripción existente. Para cancelarla, envía un PUT con el atributo status y el valor cancelled al endpoint /preapproval/{id} y ejecuta la solicitud. Para pausarla, envía un PUT con el atributo status y el valor paused al mismo endpoint y ejecuta la solicitud.
        Reactivar una suscripción	Permite reactivar una suscripción en pausa y establecer una fecha límite para su finalización. Para hacerlo, envía un PUT con los parámetros necesarios al endpoint /preapproval/{id} y ejecuta la solicitud.
        Cambiar la fecha de facturación	Para las suscripciones con una frecuencia de pago mensual, puedes elegir un día fijo del mes para que se produzca la facturación. Para hacerlo, envía un PUT con los parámetros necesarios al endpoint /preapproval/{id} y ejecuta la solicitud.
        Establecer monto proporcional	Puedes establecer un monto proporcional para facturar una suscripción en particular. Para hacerlo, envía un PUT con los parámetros necesarios al endpoint /preapproval/{id} y ejecuta la solicitud.
        Ofrecer prueba gratuita	Es posible ofrecer un período de prueba gratuito para que los clientes puedan probar el producto y/o servicio antes de comprarlo. Para ello, envía un PUT con los parámetros free_trial, frequency y frequency_type con el número y el tipo (días/meses) al endpoint /preapproval_plan/{id} y ejecuta la solicitud.
        :param preapproval_plan_id:
        :return:
        """
    url = f"https://api.mercadopago.com/preapproval_plan/{preapproval_plan_id}"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "reason": "Yoga classes",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "repetitions": 12,
            "billing_day": 10,
            "billing_day_proportional": False,
            "free_trial": {
                "frequency": 1,
                "frequency_type": "months"
            },
            "transaction_amount": 10,
            "currency_id": "ARS"
        },
        "payment_methods_allowed": {
            "payment_types": [
                {
                    "id": "credit_card"
                }
            ],
            "payment_methods": [
                {
                    "id": "bolbradesco"
                }
            ]
        },
        "back_url": "https://www.yoursite.com"

    }
    requests.put(url, headers=headers, json=create_subscription(preapproval_plan_id))
    """ SAMPLE RESPONSE
    
            {
          "id": "2c938084726fca480172750000000000",
          "application_id": 1234567812345678,
          "collector_id": 100200300,
          "reason": "Yoga classes",
          "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "repetitions": 12,
            "billing_day": 10,
            "billing_day_proportional": true,
            "free_trial": {
              "frequency": 7,
              "frequency_type": "months",
              "first_invoice_offset": 7
            },
            "transaction_amount": 10,
            "currency_id": "ARS"
          },
          "payment_methods_allowed": {
            "payment_types": [
              {}
            ],
            "payment_methods": [
              {}
            ]
          },
          "back_url": "https://www.mercadopago.com.ar",
          "external_reference": "23546246234",
          "init_point": "https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_plan_id=2c938084726fca480172750000000000",
          "date_created": "2022-01-01T11:12:25.892-04:00",
          "last_modified": "2022-01-01T11:12:25.892-04:00",
          "status": "active"
        }
    """


def create_non_preapproved_subscription():
    """
    https://www.mercadopago.com.uy/developers/es/docs/subscriptions/integration-configuration/subscription-no-associated-plan/authorized-payments
    :return:
    """

    url ="https://api.mercadopago.com/preapproval"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-scope": "stage"
    }
    payload = {
        "back_url": "https://www.google.com",
        "reason": "Test Subscription",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "start_date": "2020-06-02T13:07:14.260Z",
            "end_date": "2022-07-20T15:59:52.581Z",
            "transaction_amount": 10,
            "currency_id": "ARS"
        },
        "payer_email": "test_user+1020927396@testuser.com",
        "card_token_id": "{{CARD_TOKEN}}",
        "status": "authorized"
    }

    requests.post(url, headers=headers, json=payload)
