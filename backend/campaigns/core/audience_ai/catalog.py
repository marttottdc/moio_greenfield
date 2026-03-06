
# allowed fields from your Contact model (fullname, email, etc.)
ASSISTED_ALLOWED_FIELDS = [
    "fullname", "email", "created", "phone",
    "whatsapp_name", "company", "source", "ctype__name",
]

# natural-language synonyms → canonical field names
ASSISTED_FIELD_SYN = {
    "nombre": "fullname", "name": "fullname",
    "correo": "email", "mail": "email", "email": "email",
    "telefono": "phone", "teléfono": "phone", "phone": "phone",
    "whatsapp": "whatsapp_name", "whatsapp nombre": "whatsapp_name",
    "compañia": "company", "compañía": "company", "empresa": "company",
    "fuente": "source", "source": "source",
    "tipo": "ctype__name", "tipo de contacto": "ctype__name", "type": "ctype__name",
    "creado": "created", "created": "created",
}

# natural-language synonyms → canonical operations
ASSISTED_OP_SYN = {
    "igual": "eq", "eq": "eq", "=": "eq", "es": "eq", "is": "eq", "equals": "eq",
    "no es": "neq", "neq": "neq", "!=": "neq", "not equals": "neq",
    "contiene": "contains", "contains": "contains",
    "empieza con": "startswith", "empieza": "startswith",
    "comienza con": "startswith", "starts with": "startswith", "startswith": "startswith",
    "termina con": "endswith", "termina": "endswith",
    "ends with": "endswith", "endswith": "endswith",
    "regex": "regex", "coincide regex": "regex",
    "in": "in", "en": "in", "dentro de": "in",
    "between": "between", "entre": "between",
    "mayor que": "gt", ">": "gt", "gt": "gt",
    "mayor o igual": "gte", ">=": "gte", "gte": "gte",
    "menor que": "lt", "<": "lt", "lt": "lt",
    "menor o igual": "lte", "<=": "lte", "lte": "lte",
    "es nulo": "isnull", "isnull": "isnull", "is null": "isnull",
    "es verdadero": "istrue", "istrue": "istrue", "is true": "istrue",
    "es falso": "isfalse", "isfalse": "isfalse", "is false": "isfalse",
}
