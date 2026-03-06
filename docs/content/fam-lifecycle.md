---
title: "Fam Lifecycle"
slug: "fam-lifecycle"
category: "integrations"
order: 3
status: "published"
summary: "No explicit startup behavior defined."
tags: ["fam"]
---

## Overview

No explicit startup behavior defined.

# fam - Lifecycle

## Startup Behavior

No explicit startup behavior defined.

## Runtime Behavior

### Label Creation

- FamLabel.save() auto-generates QR code on first save
- QR code generated via `portal.core.tools.generate_qr_code`
- Empty mac_address converted to None for unique constraint

### Asset State Machine

- AssetTransition defines state transitions
- trigger → source → dest with optional prepare/conditions

### Asset Delegation

- Tracks assignment/unassignment of assets to customers/locations
- visibility flag controls display

## Shutdown Behavior

No explicit shutdown behavior defined.
