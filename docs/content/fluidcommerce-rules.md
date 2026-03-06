---
title: "Fluidcommerce Rules & Constraints"
slug: "fluidcommerce-rules"
category: "integrations"
order: 5
status: "published"
summary: "- (tenant, slug) unique"
tags: ["fluidcommerce"]
---

## Overview

- (tenant, slug) unique

# fluidcommerce - Invariants

## Enforced Rules

### Brand

- (tenant, slug) unique

### Category

- (tenant, slug) unique

### AttributeDefinition

- (tenant, slug) unique

### AttributeOption

- (attribute, value) unique

### Product

- (tenant, slug) unique

### ProductAttribute

- (product, attribute) unique

### ProductVariant

- (tenant, sku) unique

### VariantAttribute

- (variant, attribute) unique

### Order

- (tenant, order_number) unique

### Stock Reservation

- reserve_stock() uses SELECT FOR UPDATE for atomic operations
