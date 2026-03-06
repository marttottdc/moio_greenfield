---
title: "Fam Overview"
slug: "fam-overview"
category: "integrations"
order: 1
status: "published"
summary: "Fixed Asset Management (FAM) for physical asset tracking with QR labels, scan logging, delegation management, and compliance monitoring."
tags: ["fam"]
---

## Overview

Fixed Asset Management (FAM) for physical asset tracking with QR labels, scan logging, delegation management, and compliance monitoring.

# fam

## Responsibility

Fixed Asset Management (FAM) for physical asset tracking with QR labels, scan logging, delegation management, and compliance monitoring.

## What it Owns

- **FamLabel**: QR labels with unique company tags, auto-generated QR codes
- **FamLabelPrintConfiguration**: Label print settings (template, logo, message)
- **LabelPrintFormat**: Physical label dimensions and layout config
- **LabelLayout**: Layout templates with element definitions
- **FamAssetType/FamAssetBrand/FamAssetModel**: Asset classification hierarchy
- **AssetRecord**: Physical asset records with location tracking
- **AssetPolicy**: Compliance policies with scan requirements
- **AssetScanDetails**: Scan event logging with location
- **AssetDelegation**: Asset assignment to customers/locations
- **AssetTransition**: State machine transition definitions

## Core Components

### Label System
- Auto-generated QR codes on label creation
- Configurable print formats (size, DPI, layout)
- Multiple layout templates (square, horizontal, etc.)
- Label printing via PDF generation

### Asset Tracking
- Asset records with serial numbers, brands, models
- Location tracking (latitude/longitude)
- Last seen timestamp and location
- Compliance status monitoring

### Scan System
- QR code scanning logs
- GPS location capture
- RSSI (signal strength) logging
- Remote IP tracking

### Delegation Management
- Asset assignment to customers
- Assignment/unassignment tracking
- Location-based delegation

### Compliance Engine
- Policy-based compliance checking
- Min/max scan interval rules
- Distance tolerance configuration

## Label Generation Flow

```
FamLabel.save()
  │
  ├── Generate UUID
  │
  └── If no QR code:
      └── generate_qr_code('asset', str(id))
          └── Save to qr_code field
```

## What it Does NOT Do

- Does not handle user authentication (delegates to portal)
- Does not process payments (asset purchase tracking only)
- Does not send notifications (static data management)
