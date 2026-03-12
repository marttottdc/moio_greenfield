# Plugin Authoring Contract

## Overview

Plugins are installed as ZIP bundles from `Platform Admin -> Plugins -> Upload Plugin ZIP`.

A plugin is usable only when all checks pass:
1. Bundle is valid and loadable.
2. Platform admin approved it.
3. Tenant admin enabled it.
4. User is allowed by assignment rules.
5. Declared requirements are satisfied at runtime.

## ZIP Requirements

A valid ZIP bundle must:
- Contain exactly one `replica.plugin.json`.
- Include the file declared by `entrypoint`.
- Avoid unsafe paths (`..` or absolute paths).
- Stay within limits:
  - max ZIP size: 20 MB
  - max uncompressed size: 100 MB
- Optionally include an icon file (`icon.svg`, `icon.png`, `icon.webp`, `icon.jpg`, `icon.jpeg`).
- Include `README.md` to show in-app admin help text.

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
- `entrypoint` (relative `.py` path, e.g. `plugin.py`)

Optional fields:
- `description`
- `icon` (relative path in bundle: `.svg`, `.png`, `.webp`, `.jpg`, `.jpeg`)
- `readme` (relative markdown path, usually `README.md`)
- `tools` (list of tool target names, for example `files.read`)
- `capabilities`
- `permissions`
- `config_schema`
- `requirements`

Allowed `capabilities` values:
- `tools`
- `hooks`
- `skills`
- `services`
- `providers`
- `resources`

Allowed `permissions` values:
- `filesystem_read`
- `filesystem_write`
- `network_outbound`
- `shell_exec`
- `docker_exec`
- `db_models`
- `background_tasks`

`requirements` object shape:
- `tenant_config`: required tenant config keys
- `user_config`: required user config keys
- `tenant_credentials`: required tenant credential keys
- `user_credentials`: required user credential keys
- `assets`: relative bundle asset paths that must exist

`config_schema` notes:
- If `config_schema.properties` is omitted or empty, tenant admin UI renders no runtime config editor.
- If `requirements.tenant_config` is declared, those keys must also exist in `config_schema.properties`.

## Python Entrypoint Contract

Entrypoint module must export:

```python
def register(api):
    # register tools/hooks/skills/providers/services/resources
    return None
```

If import fails or `register(api)` is missing/not callable, plugin initialization fails and plugin remains inactive.

## Install and Activation Flow

1. Platform admin uploads ZIP.
2. Platform validates and installs if valid.
3. Platform admin approves plugin.
4. Tenant admin enables plugin and sets config/assignments.
5. Runtime activates plugin only when readiness checks pass.

## Update Behavior (Config Safe)

Updating with the same plugin `id` preserves tenant enablement and assignment records.

Tenant `plugin_config` updates are non-destructive:
- Existing keys are preserved.
- New top-level defaults from `config_schema.properties.<key>.default` are auto-filled when missing.
- Existing config keys are not auto-deleted.

## Troubleshooting

- `plugin bundle is missing replica.plugin.json`: add the manifest file.
- `plugin entrypoint is missing from the bundle`: fix `entrypoint` path or include file.
- `plugin entrypoint must export callable register(api)`: export callable `register(api)`.
- Plugin not visible to end users: verify platform approval, tenant enablement, and assignment rules.
