---
title: "Moio Platform Versioning"
slug: "moio-platform-versioning"
category: "api-reference"
order: 8
status: "published"
summary: "- Read from IMAGE_TAG environment variable - Falls back to version.txt file - Printed at startup: \"Moio Build: {version}\""
tags: ["moio_platform"]
---

## Overview

- Read from IMAGE_TAG environment variable - Falls back to version.txt file - Printed at startup: "Moio Build: {version}"

# moio_platform - Versioning

## Version Identifiers

### App Version

- Read from IMAGE_TAG environment variable
- Falls back to version.txt file
- Printed at startup: "Moio Build: {version}"

### API Version

- SPECTACULAR_SETTINGS["VERSION"]: "1.0.0"

## Compatibility Mechanisms

None explicitly defined.

## Migration Signals

None explicitly defined.
