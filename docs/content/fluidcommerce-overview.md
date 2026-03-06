---
title: "Fluidcommerce Overview"
slug: "fluidcommerce-overview"
category: "integrations"
order: 1
status: "published"
summary: "E-commerce product catalog management with inventory tracking, variant support, orders, and flexible attribute system."
tags: ["fluidcommerce"]
---

## Overview

E-commerce product catalog management with inventory tracking, variant support, orders, and flexible attribute system.

# fluidcommerce

## Responsibility

E-commerce product catalog management with inventory tracking, variant support, orders, and flexible attribute system.

## What it Owns

- **Brand**: Product brands with metadata
- **Category**: Hierarchical categories with materialized path
- **AttributeDefinition**: Attribute types (text, number, select, color, etc.)
- **AttributeOption**: Predefined values for select attributes
- **Product**: Products (SPU) with pricing, SEO, status
- **ProductVariant**: SKUs with inventory tracking and pricing
- **VariantAttribute**: Variant-defining attribute values
- **ProductAttribute**: Product-level attribute values
- **ProductMedia**: Images and videos for products/variants
- **Order**: Customer orders with status and payment tracking
- **OrderLine**: Order line items with snapshot data

## Core Components

### Product Catalog
- Hierarchical categories with path-based queries
- Flexible attribute system for filtering
- Product variants with independent pricing and inventory
- Multi-image support with primary flag

### Inventory Management
- Stock tracking per variant
- Low stock threshold alerts
- Backorder support
- Stock reservation with row locking

### Order Management
- Order status flow (pending → confirmed → processing → shipped → delivered)
- Payment status tracking
- Address snapshots on order lines
- Order totals calculation

## Category Hierarchy

```
Category (materialized path)
  │
  ├── path: "electronics"
  │   └── path: "electronics/phones"
  │       └── path: "electronics/phones/smartphones"
```

## Product-Variant Structure

```
Product (SPU - Standard Product Unit)
  │
  ├── base_price, description, category, brand
  │
  └── variants[] (SKUs)
      ├── SKU-001: Red / Small
      ├── SKU-002: Red / Medium
      └── SKU-003: Blue / Small
```

## What it Does NOT Do

- Does not handle payments (external gateway integration)
- Does not handle shipping rates (external service)
- Does not manage customer accounts (uses crm.Contact)
