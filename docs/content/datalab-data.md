---
title: "Datalab Data Model"
slug: "datalab-data"
category: "datalab"
order: 4
status: "published"
summary: "- id: UUID (PK) - storage_key: CharField (S3 key) - filename: CharField - content_type: CharField - size: PositiveIntegerField - uploaded_by: FK → User - metadata: JSONField - tenant: FK → Tenant"
tags: ["datalab"]
---

## Overview

- id: UUID (PK) - storage_key: CharField (S3 key) - filename: CharField - content_type: CharField - size: PositiveIntegerField - uploaded_by: FK → User - metadata: JSONField - tenant: FK → Tenant

# datalab - Data

## Owned Data Models

### FileAsset

- id: UUID (PK)
- storage_key: CharField (S3 key)
- filename: CharField
- content_type: CharField
- size: PositiveIntegerField
- uploaded_by: FK → User
- metadata: JSONField
- tenant: FK → Tenant

### FileSet

- id: UUID (PK)
- name: CharField
- description: TextField
- files: M2M → FileAsset
- schema_hint: JSONField
- last_snapshot: FK → Snapshot
- tenant: FK → Tenant

### DataSource

- id: UUID (PK)
- type: CharField (file, fileset, crm, resultset, snapshot)
- ref_id: UUIDField
- name: CharField
- description: TextField
- schema_json: JSONField
- acl_json: JSONField
- tenant: FK → Tenant

### ResultSet

- id: UUID (PK)
- name: CharField
- origin: CharField
- schema_json: JSONField
- row_count: PositiveIntegerField
- storage: CharField
- storage_key: CharField
- preview_json: JSONField (limited to 200 rows)
- lineage_json: JSONField
- is_json_object: BooleanField
- durability: CharField
- dataset_version: OneToOne → DatasetVersion
- created_by: FK → User
- expires_at: DateTimeField
- tenant: FK → Tenant

### Snapshot

- id: UUID (PK)
- name: CharField
- version: PositiveIntegerField
- resultset: FK → ResultSet
- description: TextField
- fileset: FK → FileSet
- created_by: FK → User
- tenant: FK → Tenant

Constraint: unique (tenant, name, version)

### AccumulationLog

- id: UUID (PK)
- snapshot: FK → Snapshot
- fileset: FK → FileSet
- processed_files: M2M → FileAsset
- row_count_added: PositiveIntegerField
- row_count_total: PositiveIntegerField
- is_rebuild: BooleanField
- tenant: FK → Tenant

### ImportProcess

- id: UUID (PK)
- name: CharField
- file_type: CharField (csv, excel, pdf)
- import_data_as_json: BooleanField
- shape_fingerprint: CharField
- shape_description: JSONField
- structural_units: JSONField
- semantic_derivations: JSONField
- contract_json: JSONField
- version: PositiveIntegerField
- is_active: BooleanField
- tenant: FK → Tenant

Constraint: unique (tenant, name, version)

### ImportRun

- id: UUID (PK)
- import_process: FK → ImportProcess
- raw_dataset: FK → FileAsset
- shape_match: JSONField
- status: CharField (success, failed)
- error_message: TextField
- resultset_ids: JSONField
- tenant: FK → Tenant

### Dataset

- id: UUID (PK)
- name: CharField
- description: TextField
- current_version: OneToOne → DatasetVersion
- created_by: FK → User
- tenant: FK → Tenant

Constraint: unique (tenant, name)

### DatasetVersion

- id: UUID (PK)
- dataset: FK → Dataset
- version_number: PositiveIntegerField
- result_set: OneToOne → ResultSet
- description: TextField
- is_current: BooleanField
- created_by: FK → User
- tenant: FK → Tenant

Constraint: unique (dataset, version_number)

## External Data Read

- portal.Tenant
- portal.MoioUser

## External Data Written

None directly.
