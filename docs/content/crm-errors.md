---
title: "Crm Error Handling"
slug: "crm-errors"
category: "crm"
order: 6
status: "published"
summary: "- Missing fullname/phone: Returns `(None, \"Full name and phone are required.\")` - ValueError: Returns `(None, str(e))` - Generic exception: Returns `(None, f\"Error creating contact: {str(e)}\")`"
tags: ["crm"]
---

## Overview

- Missing fullname/phone: Returns `(None, "Full name and phone are required.")` - ValueError: Returns `(None, str(e))` - Generic exception: Returns `(None, f"Error creating contact: {str(e)}")`

# crm - Failures

## Explicit Error Handling

### ContactService.create_contact
- Missing fullname/phone: Returns `(None, "Full name and phone are required.")`
- ValueError: Returns `(None, str(e))`
- Generic exception: Returns `(None, f"Error creating contact: {str(e)}")`

### ContactService.contact_upsert
- ContactType.DoesNotExist: Raises `ValueError`

### ContactService.promote_contact_to_user
- Contact.DoesNotExist: Returns `(None, "Contact not found")`
- Already linked: Returns `(None, "Contact is already linked to a user account")`
- No email: Returns `(None, "Contact must have an email address...")`
- Email exists: Returns `(None, f"A user with email {email} already exists")`
- Username taken: Returns `(None, f"Username {username} is already taken")`
- Transaction error: Returns `(None, f"Error creating user account: {str(e)}")`

### generic_webhook_handler
- WebhookConfig.DoesNotExist: Returns "No Handler Configured"
- Handler import error: Celery retry (60s countdown)
- Handler execution error: Celery retry (120s countdown)
- Payload storage error: Logged, continues

### woocommerce_webhook_processor
- Tenant.DoesNotExist: Implicit exception (task fails)
- Processing errors: Logged via print statements

## Expected Failure Modes

### External API Failures
- WooCommerce API errors
- DAC fulfillment API errors
- Zeta invoicing errors
- Google Maps geocoding errors
- OpenAI embedding errors

### Database Failures
- Duplicate key violations (phone/email)
- Foreign key violations
- Transaction deadlocks

### Webhook Failures
- Invalid payload structure
- Authentication failures
- Handler not found
- Handler execution timeout

## Recovery Mechanisms

### Automatic Recovery
- Celery task retries with countdown
- Soft time limit (120s) for webhooks
- Connection cleanup via Django

### Manual Recovery
- WebhookPayload storage for replay
- Order error fields for debugging
- Branch geocoded flag for retry
- Contact embedding regeneration

### Idempotency
- Contact upsert by phone (safe to retry)
- Order update by order_number
- Product import by SKU/external_id
