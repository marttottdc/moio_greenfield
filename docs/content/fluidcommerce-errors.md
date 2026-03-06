---
title: "Fluidcommerce Error Handling"
slug: "fluidcommerce-errors"
category: "integrations"
order: 6
status: "published"
summary: "- reserve_stock() returns False if insufficient stock and backorder not allowed"
tags: ["fluidcommerce"]
---

## Overview

- reserve_stock() returns False if insufficient stock and backorder not allowed

# fluidcommerce - Failures

## Explicit Error Handling

### Stock Reservation

- reserve_stock() returns False if insufficient stock and backorder not allowed

## Expected Failure Modes

- Duplicate SKU within tenant
- Insufficient stock for order
- Invalid category hierarchy
- Payment processing failures (uncertain)
