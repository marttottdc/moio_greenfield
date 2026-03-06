---
title: "Fam Rules & Constraints"
slug: "fam-rules"
category: "integrations"
order: 5
status: "published"
summary: "- FamLabel.company_tag unique globally - FamLabel.mac_address unique globally (when not null) - FamAssetType.name unique globally - FamAssetBrand.name unique globally - FamAssetModel.name unique globa"
tags: ["fam"]
---

## Overview

- FamLabel.company_tag unique globally - FamLabel.mac_address unique globally (when not null) - FamAssetType.name unique globally - FamAssetBrand.name unique globally - FamAssetModel.name unique globa

# fam - Invariants

## Enforced Rules

- FamLabel.company_tag unique globally
- FamLabel.mac_address unique globally (when not null)
- FamAssetType.name unique globally
- FamAssetBrand.name unique globally
- FamAssetModel.name unique globally
- AssetPolicy.name unique globally
- AssetTransition.trigger unique globally
- LabelPrintFormat.name unique globally
- LabelLayout.key unique globally
