---
title: "API Permissions / Contract Diff Errors"
slug: "api-permissions-diff-errors"
category: "api"
order: 99
status: "published"
summary: "Resumen de errores detectados en diff bot vs admin por endpoint: 500 en PATCH, 404/405 en details, 403 en resultsets/users."
tags: ["api", "permissions", "contract", "openclaw"]
---

## Resumen por endpoint

| Endpoint | Bot errors | Admin errors | Clasificación |
|----------|------------|--------------|---------------|
| /api/v1/crm/contact_types/ | 1 | 2 | bug/contract |
| /api/v1/crm/deals/ | 2 | 2 | bug/contract |
| /api/v1/datalab/crm/views/ | 2 | 2 | bug/contract |
| /api/v1/datalab/resultsets/ | 2 | 2 | permission |
| /api/v1/fluidcms/media/ | 2 | 2 | bug/contract |
| /api/v1/scripts/ | 1 | 1 | bug/contract |
| /api/v1/settings/integrations/ | 2 | 2 | bug/contract |
| /api/v1/users/ | 3 | 0 | permission-limited |

Detalle completo (paso, status, id, snippet del body): `/data/.openclaw/workspace/permissions_diff_table.json`

---

## Descripción por error (~300 caracteres)

### /api/v1/crm/contact_types/ (PATCH → 500)

Actualizar un contact type con PATCH dispara 500 Server Error (HTML) tanto con bot como con admin. Debería devolver 400/422 con errores de validación o un mensaje JSON, no un 500.

### /api/v1/crm/deals/ (PATCH → 500)

Hacer PATCH sobre deals existentes provoca 500 Server Error (HTML) para varios IDs, incluso como admin. Si el payload es inválido debería responder 400 con validación; si hay constraint debería ser 409, no 500.

### /api/v1/datalab/crm/views/ (detail → 404)

El listado devuelve objetos con id tipo UUID, pero el endpoint de detalle usa /views/{key}/. Usar el UUID del list como {key} devuelve 404 ("CRM View with key … not found"). Contrato/list shape inconsistente.

### /api/v1/datalab/resultsets/ (detail → 403 fenced)

Acceder al detalle de ciertos resultsets devuelve 403 con "ResultSet is fenced (ephemeral and not from Analyzer)" tanto para bot como admin. Parece restricción intencional, pero sorprende si el list los expone sin indicar que no son accesibles.

### /api/v1/fluidcms/media/ (detail → 405)

Se pueden listar media, pero el supuesto detalle GET /fluidcms/media/{id} responde 405 Method Not Allowed. Indica que falta endpoint de detalle o el schema/routing está mal: una colección listable sin lectura por id.

### /api/v1/scripts/ (PATCH → 400)

Actualizar un script devuelve 400 con validación: "Import, global, and nonlocal statements are not allowed in scripts." Esto parece comportamiento esperado del sandbox/validador (no bug), pero se registra como error en CRUD genérico.

### /api/v1/settings/integrations/ (detail → 405)

El listado incluye integraciones (ej. whatsapp, openai), pero GET /api/v1/settings/integrations/{id}/ da 405 (no hay GET). El endpoint {id}/ en schema es DELETE/CONNECT, así que la "ruta de detalle" no existe.

### /api/v1/users/ (POST → 403 solo bot)

Con openclaw-bot crear usuarios (POST /api/v1/users/) devuelve 403 "no permission". Con admin funciona. Esto es correcto por permisos, y confirma que el control de acceso está aplicado para creación de usuarios.
