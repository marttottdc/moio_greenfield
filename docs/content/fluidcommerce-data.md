---
title: "Fluidcommerce Data Model"
slug: "fluidcommerce-data"
category: "integrations"
order: 4
status: "published"
summary: "- id: UUID (PK) - name: CharField - slug: SlugField - description: TextField - logo_url, website_url: URLField - is_active: BooleanField - metadata: JSONField - tenant: FK → Tenant"
tags: ["fluidcommerce"]
---

## Overview

- id: UUID (PK) - name: CharField - slug: SlugField - description: TextField - logo_url, website_url: URLField - is_active: BooleanField - metadata: JSONField - tenant: FK → Tenant

# fluidcommerce - Data

## Owned Data Models

### Brand

- id: UUID (PK)
- name: CharField
- slug: SlugField
- description: TextField
- logo_url, website_url: URLField
- is_active: BooleanField
- metadata: JSONField
- tenant: FK → Tenant

Constraint: unique (tenant, slug)

### Category

- id: UUID (PK)
- name: CharField
- slug: SlugField
- description: TextField
- parent: FK → self
- image_url: URLField
- order: PositiveIntegerField
- is_active: BooleanField
- path: CharField (materialized path)
- depth: PositiveIntegerField
- tenant: FK → Tenant

Constraint: unique (tenant, slug)

### AttributeDefinition

- id: UUID (PK)
- name: CharField
- slug: SlugField
- attribute_type: CharField
- is_variant_attribute: BooleanField
- is_filterable: BooleanField
- is_required: BooleanField
- order: PositiveIntegerField
- tenant: FK → Tenant

Constraint: unique (tenant, slug)

### AttributeOption

- id: UUID (PK)
- attribute: FK → AttributeDefinition
- value: CharField
- label: CharField
- color_hex: CharField
- order: PositiveIntegerField

Constraint: unique (attribute, value)

### Product

- id: UUID (PK)
- name: CharField
- slug: SlugField
- description, short_description: TextField/CharField
- brand: FK → Brand
- category: FK → Category
- status: CharField
- base_price, compare_at_price, cost_price: DecimalField
- currency: CharField
- tax_class: CharField
- is_taxable: BooleanField
- weight: DecimalField
- weight_unit: CharField
- has_variants: BooleanField
- seo_title, seo_description: CharField/TextField
- metadata: JSONField
- tenant: FK → Tenant

Constraint: unique (tenant, slug)

### ProductAttribute

- id: UUID (PK)
- product: FK → Product
- attribute: FK → AttributeDefinition
- value_text: TextField
- value_number: DecimalField
- value_boolean: BooleanField
- value_option: FK → AttributeOption
- value_options: M2M → AttributeOption

Constraint: unique (product, attribute)

### ProductVariant

- id: UUID (PK)
- product: FK → Product
- sku: CharField
- barcode: CharField
- name: CharField
- price, compare_at_price, cost_price: DecimalField
- stock_quantity: IntegerField
- low_stock_threshold: PositiveIntegerField
- track_inventory: BooleanField
- allow_backorder: BooleanField
- weight: DecimalField
- is_active: BooleanField
- position: PositiveIntegerField
- metadata: JSONField
- tenant: FK → Tenant

Constraint: unique (tenant, sku)

### VariantAttribute

- id: UUID (PK)
- variant: FK → ProductVariant
- attribute: FK → AttributeDefinition
- option: FK → AttributeOption

Constraint: unique (variant, attribute)

### ProductMedia

- id: UUID (PK)
- product: FK → Product
- variant: FK → ProductVariant (nullable)
- url: URLField
- alt_text: CharField
- media_type: CharField
- is_primary: BooleanField
- position: PositiveIntegerField
- tenant: FK → Tenant

### Order

- id: UUID (PK)
- order_number: CharField
- customer_email: EmailField
- customer_name, customer_phone: CharField
- contact: FK → crm.Contact
- status: CharField
- payment_status: CharField
- subtotal, discount_amount, tax_amount, shipping_amount, total: DecimalField
- currency: CharField
- shipping_address, billing_address: JSONField
- notes, internal_notes: TextField
- metadata: JSONField
- placed_at, shipped_at, delivered_at, cancelled_at: DateTimeField
- tenant: FK → Tenant

Constraint: unique (tenant, order_number)

### OrderLine

- id: UUID (PK)
- order: FK → Order
- variant: FK → ProductVariant (nullable)
- product_name, variant_name: CharField
- sku: CharField
- quantity: PositiveIntegerField
- unit_price, discount_amount, tax_amount, total: DecimalField
- metadata: JSONField

## External Data Read

- crm.Contact
- portal.Tenant

## External Data Written

None directly.
