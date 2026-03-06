from crm.lib.mercadopago_api import create_subscription, create_suscription_plan

create_suscription_plan()
sid = input("ingresa el suscription_id: ")
create_subscription(sid)

"""
APRO	Pago aprobado	(CI) 12345678 (otro) 123456789
OTHE	Rechazado por error general	(CI) 12345678 (otro) 123456789
CONT	Pendiente de pago	-
CALL	Rechazado con validación para autorizar	-
FUND	Rechazado por importe insuficiente	-
SECU	Rechazado por código de seguridad inválido	-
EXPI	Rechazado debido a un problema de fecha de vencimiento	-
FORM	Rechazado debido a un error de formulario	-
CARD	Rechazado por falta de card_number	-
INST	Rechazado por cuotas invalidas	-
DUPL	Rechazado por pago duplicado	-
LOCK	Rechazado por tarjeta deshabilitada	-
CTNA	Rechazado por tipo de tarjeta no permitida	-
ATTE	Rechazado debido a intentos excedidos del pin de la tarjeta	-
BLAC	Rechazado por estar en lista negra	-
UNSU	No soportado	-
TEST	Usado para aplicar regla de montos

"""