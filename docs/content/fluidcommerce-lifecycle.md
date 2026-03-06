---
title: "Fluidcommerce Lifecycle"
slug: "fluidcommerce-lifecycle"
category: "integrations"
order: 3
status: "published"
summary: "No explicit startup behavior defined."
tags: ["fluidcommerce"]
---

## Overview

No explicit startup behavior defined.

# fluidcommerce - Lifecycle

## Startup Behavior

No explicit startup behavior defined.

## Runtime Behavior

### Slug Generation

- Brand, Category, AttributeDefinition, Product auto-generate slug from name if not set

### Category Path

- Category.save() updates path and depth based on parent
- Descendants' paths updated when parent path changes
- path format: "parent-slug/child-slug/grandchild-slug"

### Attribute Labels

- AttributeOption.save() sets label from value if not set

### Variant Pricing

- ProductVariant.effective_price property returns variant price or falls back to product base_price

### Inventory Management

- ProductVariant.is_in_stock: True if not tracking or quantity > 0 or allow_backorder
- ProductVariant.is_low_stock: True if tracking and 0 < quantity <= threshold
- adjust_stock(): Modifies stock_quantity
- reserve_stock(): Atomic decrement with row locking

### Order Lifecycle

- Order.confirm(): Sets status to CONFIRMED, placed_at
- Order.ship(): Sets status to SHIPPED, shipped_at
- Order.deliver(): Sets status to DELIVERED, delivered_at
- Order.cancel(): Sets status to CANCELLED, cancelled_at, appends reason to internal_notes
- Order.calculate_totals(): Recalculates subtotal and total from lines

### Order Line Totals

- OrderLine.save() calculates total from unit_price * quantity - discount + tax

## Shutdown Behavior

No explicit shutdown behavior defined.
