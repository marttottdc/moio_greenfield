# Roles y capabilities: ¿Django permissions / Groups o modelo propio?

## Situación actual

- **Roles** = nombres de **Django Group** (viewer, member, manager, tenant_admin, platform_admin). El tenant admin asigna a cada usuario **un** grupo (role).
- **Capabilities** (permisos granulares: crm_contacts_read, users_manage, etc.) están **en código**: `ROLE_CAPABILITIES[role]` en `tenancy/capabilities.py`. No se pueden editar desde Platform Admin.

## ¿Podemos usar los permisos normales de Django?

**Sí.** Opción típica:

1. Definir un modelo (ej. `AppCapability`) con `Meta.permissions = [(codename, name), ...]` para cada capability.
2. Hacer migración → se crean filas en `auth_permission`.
3. Cada **rol** = un **Group**; asignas al grupo los `Permission` que correspondan.
4. En código: `eff.can("crm_contacts_read")` → `user.has_perm("tenancy.crm_contacts_read")` y se cruza con lo que permite el plan del tenant.

**Ventaja:** estándar Django, integración con admin y con `has_perm`.  
**Desventaja:** añadir un permiso nuevo = cambiar `Meta.permissions` y **migración**. Para “crear muchos más” permisos, las migraciones se multiplican.

## ¿Por qué no usar solo Groups como roles?

**De hecho ya usamos Groups como roles:** el “rol” del usuario es el **nombre del grupo** al que pertenece. La diferencia es:

- **Hoy:** las capabilities de cada rol están **hardcodeadas** en `ROLE_CAPABILITIES` (Python). El Group solo identifica el rol; qué puede hacer ese rol está en código.
- **Con permisos Django:** las capabilities serían **Permission** asignadas a cada Group. El Group seguiría siendo el rol; qué puede hacer se leería de la base de datos (Group ↔ Permission).

Así que la pregunta no es “¿usamos Groups?” (ya los usamos), sino **dónde guardamos “qué puede hacer este rol”**: en código (dict) o en BD (Permission en Group, o modelo propio).

## Diferencia: Django Permission en Groups vs modelo Role propio

| | Django Group + Permission | Modelo Role + Capability (M2M) |
|--|---------------------------|--------------------------------|
| **Dónde se guarda “este rol puede X”** | Group tiene M2M a `auth.Permission` | Tabla `Role` con M2M a `Capability` |
| **Añadir muchos permisos nuevos** | Nueva capability = nuevo `Permission` → migración (o fixture) | Nueva capability = fila en `Capability` (o lista en código + seed). Sin migración si no cambias modelo. |
| **Quién crea/edita roles** | Admin de Django (Groups) o UI custom que filtre solo “nuestros” permissions | Platform Admin: CRUD de Roles y checkboxes de capabilities |
| **Asignación a usuarios** | Igual: usuario en un Group (rol) | Igual: usuario en un Group; el slug del rol = nombre del Group |

Para tener **un creador de roles en Platform Admin** y **muchos más permisos** sin depender de migraciones por cada uno, conviene:

- **Modelo propio:** `Capability` (key, label, descripción) y `Role` (name, slug, display_order, M2M a Capability).
- Al guardar un Role, se crea/actualiza un **Group** con `name=slug`, para que la asignación de usuarios siga siendo “elegir un grupo” en tenant admin.
- El resolver de capabilities (`get_effective_capabilities`) deja de usar solo `ROLE_CAPABILITIES` y, para cada grupo del usuario, busca el Role por slug y toma las capabilities del Role; luego cruza con lo que permite el plan del tenant.

Así los roles son “combinaciones de features” editables en Platform Admin, disponibles para todos los tenant admins para asignar (uno) a cada usuario, y podemos crear muchos más permisos solo añadiendo filas en `Capability` (o seeds) sin tocar el modelo con migraciones.
