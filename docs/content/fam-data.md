---
title: "Fam Data Model"
slug: "fam-data"
category: "integrations"
order: 4
status: "published"
summary: "- id: UUID (PK) - company_tag: CharField (unique) - qr_code: ImageField - mac_address: CharField (unique, nullable) - printed_at: DateTimeField - printed_by: FK → User - tenant: FK → Tenant"
tags: ["fam"]
---

## Overview

- id: UUID (PK) - company_tag: CharField (unique) - qr_code: ImageField - mac_address: CharField (unique, nullable) - printed_at: DateTimeField - printed_by: FK → User - tenant: FK → Tenant

# fam - Data

## Owned Data Models

### FamLabel

- id: UUID (PK)
- company_tag: CharField (unique)
- qr_code: ImageField
- mac_address: CharField (unique, nullable)
- printed_at: DateTimeField
- printed_by: FK → User
- tenant: FK → Tenant

### FamLabelPrintConfiguration

- name: CharField (unique)
- print_template_id: CharField
- logo: ImageField
- custom_message: CharField
- show_company_tag, show_logo, show_custom_message, show_mac_address, show_creation_date: BooleanField
- tenant: FK → Tenant

### FamAssetType

- name: CharField (unique)
- description: TextField
- tenant: FK → Tenant

### FamAssetBrand

- name: CharField (unique)
- description: TextField
- tenant: FK → Tenant

### FamAssetModel

- brand: FK → FamAssetBrand
- name: CharField (unique)
- description: TextField
- tenant: FK → Tenant

### AssetPolicy

- name: CharField (unique)
- description: CharField
- min_days, max_days: IntegerField
- read_method: CharField
- enabled: BooleanField
- distance_tolerance: IntegerField
- tenant: FK → Tenant

### AssetRecord

- serial_number, brand, model, name: CharField
- type: FK → FamAssetType
- purchase_date: DateField
- status: CharField
- last_seen: BigIntegerField
- last_location: CharField
- last_known_latitude, last_known_longitude: DecimalField
- comment: TextField
- owner_company: CharField
- asset_image: ImageField
- active, compliant: BooleanField
- policy: FK → AssetPolicy
- label: FK → FamLabel
- tenant: FK → Tenant

### AssetScanDetails

- rssi: IntegerField
- latitude, longitude: DecimalField
- scanned_by: CharField
- received_date: DateTimeField
- full_body: JSONField
- url: URLField
- label_id: UUIDField
- remote_ip, info: CharField/TextField
- tenant: FK → Tenant

### AssetDelegation

- asset_id: FK → AssetRecord
- customer_id: FK → Customer
- assigned_location: FK → Address
- assigned_on, unassigned_on: DateTimeField
- comment: TextField
- status: CharField
- visible: BooleanField
- tenant: FK → Tenant

### AssetTransition

- enabled: BooleanField
- trigger: CharField (unique)
- source, dest: CharField
- prepare, conditions: CharField
- tenant: FK → Tenant

### LabelPrintFormat

- name: CharField (unique)
- layout_key: CharField
- width_mm, height_mm: DecimalField
- dpi: PositiveIntegerField
- bleed_mm: DecimalField
- page, orient: CharField
- cols, rows: PositiveIntegerField
- cell_w_mm, cell_h_mm, gap_x_mm, gap_y_mm, margin_mm: DecimalField
- main_text, code_text, sample_code: CharField
- mappings: JSONField
- tenant: FK → Tenant

### LabelLayout

- key: SlugField (unique)
- description: CharField
- elements: JSONField
- logo: ImageField
- tenant: FK → Tenant

## External Data Read

- crm.Customer
- crm.Address
- portal.Tenant
- portal.MoioUser

## External Data Written

None directly.
