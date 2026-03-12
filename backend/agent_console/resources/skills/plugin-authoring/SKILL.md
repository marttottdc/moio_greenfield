---
name: plugin-authoring
description: Create and review Replica plugin ZIP bundles for platform upload. Use when building or validating `replica.plugin.json`, implementing the Python `register(api)` entrypoint, selecting capabilities/permissions, wiring requirements/config_schema, packaging README/icon/assets, or troubleshooting why a plugin is inactive or not visible.
---

# Plugin Authoring

## Overview

Author plugin bundles that pass upload-time validation and runtime readiness checks. Use the templates in `assets/` to scaffold files, and use `references/plugin-contract.md` to verify contract details.

## Workflow

1. Confirm plugin scope and runtime needs.
- Define plugin `id`, feature scope, and the resources it will expose (`tools`, `hooks`, `skills`, `services`, `providers`, `resources`).
- Request only permissions required by those features.
- Decide required tenant/user config and credentials before writing the manifest.

2. Scaffold bundle files.
- Start from `assets/replica.plugin.template.json` and fill required fields.
- Use `assets/plugin.py` as the entrypoint skeleton and keep `register(api)` callable.
- Add `README.md` (optional but recommended for in-app admin help text).
- Add icon file if desired (`.svg`, `.png`, `.webp`, `.jpg`, `.jpeg`).

3. Validate manifest semantics.
- Enforce `schema_version = 1`.
- Enforce plugin id regex: `^[a-z0-9][a-z0-9._-]{0,79}$`.
- Keep `entrypoint` as a relative `.py` path included in the bundle.
- Restrict `capabilities` and `permissions` to allowed values.
- If `requirements.tenant_config` is set, include matching keys in `config_schema.properties`.

4. Validate bundle structure.
- Ensure exactly one `replica.plugin.json` exists in the ZIP.
- Ensure ZIP has no unsafe paths (`..` or absolute paths).
- Ensure `entrypoint` exists in ZIP.
- Keep ZIP within limits: 20 MB compressed, 100 MB uncompressed.

5. Check activation path when debugging visibility.
- Platform admin upload and approval.
- Tenant admin enablement and assignment.
- User included by assignment rules.
- Runtime requirements satisfied (`tenant_config`, credentials, assets, etc.).

## Output Checklist

Before finalizing, verify all are true:
- ZIP contains exactly one `replica.plugin.json`.
- Entrypoint module imports and exports callable `register(api)`.
- Manifest required fields are present and valid.
- Optional `requirements.assets` files exist in bundle.
- Capability/permission sets are valid and minimal.
- `requirements.tenant_config` keys exist in `config_schema.properties`.
- Bundle size/path safety constraints are satisfied.

## References

- Use `references/plugin-contract.md` for full manifest, ZIP, lifecycle, and troubleshooting rules.
- Use `assets/` templates to generate initial files quickly.
