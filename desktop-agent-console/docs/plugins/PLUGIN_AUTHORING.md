# Plugin Authoring Guide

## Overview

Plugins are installed as ZIP bundles from **Platform Admin → Plugins → Upload Plugin ZIP**.

A plugin is considered usable only when all of these are true:

1. Bundle is valid and loadable.
2. Platform admin approved it.
3. Tenant admin enabled it.
4. User is allowed by assignment rules.
5. Declared requirements are satisfied at runtime.

## ZIP Requirements

Your ZIP must:

- contain **exactly one** `replica.plugin.json`
- include the `entrypoint` file declared in the manifest
- avoid unsafe paths (`..` or absolute paths)
- be within size limits:
  - max ZIP size: **20 MB**
  - max uncompressed size: **100 MB**
- optionally include an icon file (`icon.svg`, `icon.png`, `icon.webp`, `icon.jpg`, or `icon.jpeg`)
- include `README.md` if you want in-app plugin help text (shown to platform/tenant admins)

Example structure:

```text
my-plugin.zip
└── my-plugin/
    ├── replica.plugin.json
    ├── plugin.py
    ├── README.md
    ├── icon.svg
    └── openapi.json
```

## Manifest Contract (`replica.plugin.json`)

Required fields:

- `schema_version` (must be `1`)
- `id` (regex: `^[a-z0-9][a-z0-9._-]{0,79}$`)
- `name`
- `version`
- `entrypoint` (relative `.py` path, for example `plugin.py`)

Optional fields:

- `description`
- `icon` (relative icon path inside bundle: `.svg`, `.png`, `.webp`, `.jpg`, `.jpeg`)
- `readme` (relative markdown path, usually `README.md`)
- `tools` (list of tool target names, for example `["files.read"]`)
- `capabilities`
- `permissions`
- `config_schema`
- `requirements`

Allowed `capabilities`:

- `tools`
- `hooks`
- `skills`
- `services`
- `providers`
- `resources`

Allowed `permissions`:

- `filesystem_read`
- `filesystem_write`
- `network_outbound`
- `shell_exec`
- `docker_exec`
- `db_models`
- `background_tasks`

`requirements` shape:

- `tenant_config`: list of tenant config keys required
- `user_config`: list of user config keys required
- `tenant_credentials`: list of tenant credential keys required
- `user_credentials`: list of user credential keys required
- `assets`: list of relative asset paths that must exist in the bundle

If `config_schema.properties` is omitted or empty, tenant admin UI will treat the plugin as having no runtime config fields and will not render a config editor.
If `requirements.tenant_config` is declared, those keys must also exist in `config_schema.properties`.

## Python Entrypoint Contract

The entrypoint module must export a callable:

```python
def register(api):
    # register tools/hooks/skills/providers/services/resources
    return None
```

If module import fails or `register(api)` is missing/not callable, the plugin will fail initialization and remain inactive.

## Minimal Example

`replica.plugin.json`:

```json
{
  "schema_version": 1,
  "id": "crm.contacts",
  "name": "CRM Contacts",
  "version": "1.0.0",
  "description": "CRM contact lookup and updates",
  "entrypoint": "plugin.py",
  "icon": "icon.svg",
  "readme": "README.md",
  "tools": ["files.read"],
  "capabilities": ["tools", "resources"],
  "permissions": ["network_outbound"],
  "requirements": {
    "tenant_config": ["base_url"],
    "tenant_credentials": ["crm_api_key"],
    "assets": ["openapi.json"]
  }
}
```

`plugin.py`:

```python
def register(api):
    # Example only; register actual plugin resources here.
    return None
```

## Install Flow

1. Platform admin uploads ZIP.
2. Platform sets plugin as installed/validated (if valid).
3. Platform admin toggles approval.
4. Tenant admin enables plugin and sets config/assignments.
5. Runtime activates only when readiness checks pass.

## Update Behavior (Config Safe)

Updating a plugin bundle with the same `id` keeps tenant enablement and assignment records.

For tenant `plugin_config`, update behavior is non-destructive:

- existing keys are preserved
- new top-level defaults from `config_schema.properties.<key>.default` are auto-filled when missing
- no existing config keys are deleted automatically

## Troubleshooting

- **“plugin bundle is missing replica.plugin.json”**: add manifest file.
- **“plugin entrypoint is missing from the bundle”**: fix `entrypoint` path or include file.
- **“plugin entrypoint must export callable register(api)”**: add `register(api)` function.
- **Not visible to user**: check platform approval, tenant enablement, and assignment rules.
