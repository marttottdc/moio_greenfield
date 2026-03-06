# Additional API Endpoints and Specifications

## Settings API - Extended

### User Management

#### GET `/settings/users`
List all users in the organization.

**Query Parameters:**
- `page` (integer, default: 1)
- `limit` (integer, default: 50)
- `role` (string): Filter by role (admin|manager|user|agent)
- `status` (string): Filter by status (active|inactive|suspended)
- `search` (string): Search by name or email

**Response (200 OK):**
```json
{
  "users": [
    {
      "id": "uuid",
      "username": "maria.garcia",
      "email": "maria@moiodigital.com",
      "full_name": "María García",
      "role": "manager",
      "status": "active",
      "avatar_url": "https://cdn.moio.com/avatars/maria.jpg",
      "permissions": ["contacts.write", "tickets.write", "campaigns.write"],
      "last_login": "2025-11-12T10:30:00Z",
      "created_at": "2025-01-15T09:00:00Z"
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 1,
    "total_items": 5
  }
}
```

---

#### POST `/settings/users`
Create a new user.

**Request Body:**
```json
{
  "username": "juan.perez",
  "email": "juan@moiodigital.com",
  "full_name": "Juan Pérez",
  "password": "SecurePassword123!",
  "role": "user",
  "permissions": ["contacts.read", "tickets.write"]
}
```

**Response (201 Created):**
```json
{
  "id": "uuid",
  "username": "juan.perez",
  "email": "juan@moiodigital.com",
  "full_name": "Juan Pérez",
  "role": "user",
  "status": "active",
  "created_at": "2025-11-12T10:30:00Z"
}
```

---

#### PATCH `/settings/users/{id}`
Update user details or permissions.

**Request Body:**
```json
{
  "role": "manager",
  "status": "active",
  "permissions": ["contacts.write", "tickets.write", "deals.write"]
}
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "role": "manager",
  "status": "active",
  "permissions": ["contacts.write", "tickets.write", "deals.write"],
  "updated_at": "2025-11-12T10:35:00Z"
}
```

---

#### DELETE `/settings/users/{id}`
Deactivate or delete a user.

**Query Parameters:**
- `hard_delete` (boolean, default: false): Permanently delete vs deactivate

**Response (200 OK):**
```json
{
  "message": "User deactivated successfully"
}
```

---

### Organization Settings

#### GET `/settings/organization`
Get organization-level settings.

**Response (200 OK):**
```json
{
  "organization": {
    "id": "uuid",
    "name": "Tienda Inglesa",
    "slug": "tienda-inglesa",
    "industry": "retail",
    "logo_url": "https://cdn.moio.com/orgs/tienda-inglesa/logo.png",
    "timezone": "America/Montevideo",
    "locale": "es_UY",
    "currency": "UYU",
    "date_format": "DD/MM/YYYY",
    "time_format": "24h",
    "business_hours": {
      "monday": {"start": "09:00", "end": "18:00"},
      "tuesday": {"start": "09:00", "end": "18:00"},
      "wednesday": {"start": "09:00", "end": "18:00"},
      "thursday": {"start": "09:00", "end": "18:00"},
      "friday": {"start": "09:00", "end": "18:00"},
      "saturday": null,
      "sunday": null
    },
    "contact_info": {
      "email": "info@tiendainglesa.com.uy",
      "phone": "+598 XXXX XXXX",
      "address": "Montevideo, Uruguay"
    }
  }
}
```

---

#### PATCH `/settings/organization`
Update organization settings.

**Request Body:**
```json
{
  "name": "Tienda Inglesa SA",
  "timezone": "America/Montevideo",
  "business_hours": {
    "saturday": {"start": "10:00", "end": "14:00"}
  }
}
```

**Response (200 OK):**
```json
{
  "message": "Organization settings updated",
  "updated_at": "2025-11-12T10:40:00Z"
}
```

---

### Notification Settings

#### GET `/settings/notifications`
Get notification configuration.

**Response (200 OK):**
```json
{
  "channels": {
    "email": {
      "enabled": true,
      "smtp_host": "smtp.gmail.com",
      "smtp_port": 587,
      "from_address": "notifications@moiodigital.com",
      "from_name": "Moio CRM"
    },
    "sms": {
      "enabled": false,
      "provider": null
    },
    "push": {
      "enabled": true,
      "provider": "firebase"
    }
  },
  "templates": [
    {
      "id": "new_ticket",
      "name": "New Ticket Notification",
      "channels": ["email", "push"],
      "recipients": ["assigned_user", "admin"]
    },
    {
      "id": "campaign_completed",
      "name": "Campaign Completed",
      "channels": ["email"],
      "recipients": ["campaign_creator", "admin"]
    }
  ]
}
```

---

#### PATCH `/settings/notifications`
Update notification settings.

**Request Body:**
```json
{
  "channels": {
    "email": {
      "enabled": true,
      "smtp_host": "smtp.sendgrid.net"
    }
  }
}
```

**Response (200 OK):**
```json
{
  "message": "Notification settings updated"
}
```

---

### Roles & Permissions

#### GET `/settings/roles`
List all available roles and their permissions.

**Response (200 OK):**
```json
{
  "roles": [
    {
      "id": "admin",
      "name": "Administrator",
      "description": "Full system access",
      "permissions": ["*"],
      "user_count": 2
    },
    {
      "id": "manager",
      "name": "Manager",
      "description": "Manage teams and campaigns",
      "permissions": [
        "contacts.read", "contacts.write",
        "tickets.read", "tickets.write",
        "campaigns.read", "campaigns.write",
        "flows.read", "flows.write",
        "users.read"
      ],
      "user_count": 3
    },
    {
      "id": "agent",
      "name": "Agent",
      "description": "Handle customer interactions",
      "permissions": [
        "contacts.read",
        "tickets.read", "tickets.write",
        "communications.read", "communications.write"
      ],
      "user_count": 15
    }
  ]
}
```

---

## Contacts API - Extended

### Batch Operations

#### POST `/contacts/batch`
Perform batch operations on multiple contacts.

**Request Body:**
```json
{
  "operation": "update|delete|tag|export",
  "contact_ids": ["uuid1", "uuid2", "uuid3"],
  "data": {
    "type": "Customer",
    "tags": ["vip"]
  }
}
```

**Response (200 OK):**
```json
{
  "message": "Batch operation completed",
  "processed": 3,
  "failed": 0,
  "results": [
    {
      "contact_id": "uuid1",
      "status": "success"
    },
    {
      "contact_id": "uuid2",
      "status": "success"
    },
    {
      "contact_id": "uuid3",
      "status": "success"
    }
  ]
}
```

---

### Tag Management

#### GET `/contacts/tags`
List all available contact tags.

**Response (200 OK):**
```json
{
  "tags": [
    {
      "name": "vip",
      "color": "#ff6b6b",
      "contact_count": 47
    },
    {
      "name": "priority",
      "color": "#ffba08",
      "contact_count": 123
    },
    {
      "name": "interested",
      "color": "#74c365",
      "contact_count": 245
    }
  ]
}
```

---

#### POST `/contacts/{id}/tags`
Add tags to a contact.

**Request Body:**
```json
{
  "tags": ["vip", "priority", "confirmed"]
}
```

**Response (200 OK):**
```json
{
  "contact_id": "uuid",
  "tags": ["vip", "priority", "confirmed", "existing-tag"]
}
```

---

#### DELETE `/contacts/{id}/tags`
Remove tags from a contact.

**Request Body:**
```json
{
  "tags": ["old-tag"]
}
```

**Response (200 OK):**
```json
{
  "contact_id": "uuid",
  "tags": ["vip", "priority"]
}
```

---

### Segments

#### GET `/contacts/segments`
List all contact segments.

**Response (200 OK):**
```json
{
  "segments": [
    {
      "id": "uuid",
      "name": "Hot Leads",
      "description": "Leads with high engagement",
      "filters": {
        "type": "Lead",
        "tags": ["interested"],
        "last_contact_within": "7 days"
      },
      "contact_count": 234,
      "created_at": "2025-10-01T10:00:00Z"
    }
  ]
}
```

---

#### POST `/contacts/segments`
Create a new segment.

**Request Body:**
```json
{
  "name": "Confirmed Candidates",
  "description": "Candidates who confirmed interview",
  "filters": {
    "type": "Lead",
    "tags": ["confirmed"],
    "created_after": "2025-11-01T00:00:00Z"
  }
}
```

**Response (201 Created):**
```json
{
  "id": "uuid",
  "name": "Confirmed Candidates",
  "contact_count": 89,
  "created_at": "2025-11-12T10:45:00Z"
}
```

---

### Contact Activity

#### GET `/contacts/{id}/activity`
Get complete activity history for a contact.

**Query Parameters:**
- `type` (string): Filter by activity type
- `limit` (integer, default: 50)
- `page` (integer, default: 1)

**Response (200 OK):**
```json
{
  "activities": [
    {
      "id": "uuid",
      "type": "message_sent",
      "description": "WhatsApp message sent via campaign",
      "metadata": {
        "campaign_id": "uuid",
        "campaign_name": "Confirmacion Punta",
        "message": "Hola Luis, te confirmamos..."
      },
      "timestamp": "2025-11-11T10:00:00Z"
    },
    {
      "id": "uuid",
      "type": "ticket_created",
      "description": "Support ticket created",
      "metadata": {
        "ticket_id": "uuid",
        "subject": "Consulta sobre horarios"
      },
      "timestamp": "2025-11-10T15:30:00Z"
    },
    {
      "id": "uuid",
      "type": "contact_updated",
      "description": "Contact type changed from Lead to Customer",
      "metadata": {
        "field": "type",
        "old_value": "Lead",
        "new_value": "Customer"
      },
      "performed_by": {
        "id": "uuid",
        "name": "María García"
      },
      "timestamp": "2025-11-09T11:20:00Z"
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 5,
    "total_items": 247
  }
}
```

---

### Contact Merge

#### POST `/contacts/merge`
Merge duplicate contacts.

**Request Body:**
```json
{
  "primary_contact_id": "uuid1",
  "duplicate_contact_ids": ["uuid2", "uuid3"],
  "merge_strategy": "keep_primary|merge_all",
  "fields_to_merge": ["tags", "custom_fields", "activity"]
}
```

**Response (200 OK):**
```json
{
  "merged_contact": {
    "id": "uuid1",
    "name": "LUIS ZAPATA",
    "phone": "+59892637130",
    "email": "luis.zapata@example.com",
    "tags": ["vip", "priority", "merged"],
    "activity_count": 47
  },
  "deleted_contacts": ["uuid2", "uuid3"],
  "message": "Contacts merged successfully"
}
```

---

## Communications API - Extended

### Message Send with Attachments

#### POST `/communications/messages/send`
Send a message with full attachment support.

**Request Body:**
```json
{
  "contact_id": "uuid",
  "channel": "WhatsApp",
  "message": {
    "type": "text|image|video|audio|document",
    "content": "Hola! Te enviamos la confirmación adjunta.",
    "attachments": [
      {
        "type": "document",
        "file_id": "uuid",
        "filename": "confirmacion.pdf",
        "mime_type": "application/pdf",
        "size": 245678
      }
    ],
    "template_id": "uuid",
    "template_variables": {
      "name": "Luis",
      "date": "12/11/2025"
    }
  },
  "metadata": {
    "campaign_id": "uuid",
    "context": "interview_confirmation"
  }
}
```

**Response (201 Created):**
```json
{
  "message_id": "uuid",
  "conversation_id": "uuid",
  "status": "queued",
  "queued_at": "2025-11-12T10:50:00Z",
  "estimated_delivery": "2025-11-12T10:50:05Z"
}
```

---

### Message Status & Delivery Receipts

#### GET `/communications/messages/{id}/status`
Get message delivery status and read receipts.

**Response (200 OK):**
```json
{
  "message_id": "uuid",
  "conversation_id": "uuid",
  "status": "sent|delivered|read|failed",
  "timeline": [
    {
      "status": "queued",
      "timestamp": "2025-11-12T10:50:00Z"
    },
    {
      "status": "sent",
      "timestamp": "2025-11-12T10:50:02Z"
    },
    {
      "status": "delivered",
      "timestamp": "2025-11-12T10:50:05Z"
    },
    {
      "status": "read",
      "timestamp": "2025-11-12T10:52:30Z"
    }
  ],
  "error": null
}
```

---

### Attachment Upload

#### POST `/communications/attachments`
Upload an attachment for use in messages.

**Request (multipart/form-data):**
```
file: (binary)
type: image|video|audio|document
```

**Response (201 Created):**
```json
{
  "file_id": "uuid",
  "url": "https://cdn.moio.com/attachments/abc123.jpg",
  "filename": "image.jpg",
  "mime_type": "image/jpeg",
  "size": 1234567,
  "type": "image",
  "expires_at": "2025-12-12T10:50:00Z"
}
```

---

### Channel Configuration

#### GET `/communications/channels`
List all configured communication channels.

**Response (200 OK):**
```json
{
  "channels": [
    {
      "id": "whatsapp_business",
      "name": "WhatsApp Business",
      "type": "WhatsApp",
      "status": "active",
      "config": {
        "phone_number": "+598XXXXXXXXX",
        "business_name": "Tienda Inglesa",
        "verified": true
      },
      "capabilities": ["text", "image", "video", "audio", "document", "location"],
      "message_limit": {
        "daily": 10000,
        "used_today": 1247
      },
      "last_sync": "2025-11-12T10:45:00Z"
    },
    {
      "id": "email_main",
      "name": "Email - Main",
      "type": "Email",
      "status": "active",
      "config": {
        "from_address": "notifications@tiendainglesa.com.uy"
      },
      "capabilities": ["text", "html", "attachments"]
    }
  ]
}
```

---

### Conversation Assignment

#### POST `/communications/conversations/{id}/assign`
Assign conversation to a user.

**Request Body:**
```json
{
  "user_id": "uuid",
  "note": "Escalating to manager for approval"
}
```

**Response (200 OK):**
```json
{
  "conversation_id": "uuid",
  "assigned_to": {
    "id": "uuid",
    "name": "María García",
    "email": "maria@moiodigital.com"
  },
  "assigned_at": "2025-11-12T10:55:00Z"
}
```

---

### Bulk Message Status

#### POST `/communications/messages/status/bulk`
Get status for multiple messages at once.

**Request Body:**
```json
{
  "message_ids": ["uuid1", "uuid2", "uuid3"]
}
```

**Response (200 OK):**
```json
{
  "messages": [
    {
      "id": "uuid1",
      "status": "delivered"
    },
    {
      "id": "uuid2",
      "status": "read"
    },
    {
      "id": "uuid3",
      "status": "failed",
      "error": "Invalid phone number"
    }
  ]
}
```

---

## Campaigns API - Extended

### Template Management

#### GET `/campaigns/templates`
List all message templates.

**Query Parameters:**
- `channel` (string): Filter by channel
- `category` (string): Filter by category
- `status` (string): Filter by approval status (approved|pending|rejected)
- `page`, `limit`: Pagination

**Response (200 OK):**
```json
{
  "templates": [
    {
      "id": "uuid",
      "name": "Confirmación de Entrevista",
      "channel": "WhatsApp",
      "category": "recruitment",
      "language": "es",
      "status": "approved",
      "content": "Hola {{name}}, te confirmamos tu entrevista para el {{date}} a las {{time}}. Por favor confirma tu asistencia respondiendo SÍ a este mensaje.",
      "variables": ["name", "date", "time"],
      "buttons": [
        {
          "type": "quick_reply",
          "text": "SÍ"
        },
        {
          "type": "quick_reply",
          "text": "NO"
        }
      ],
      "header": {
        "type": "text",
        "content": "Entrevista Confirmada"
      },
      "footer": {
        "content": "Tienda Inglesa - RRHH"
      },
      "created_at": "2025-10-15T10:00:00Z",
      "approved_at": "2025-10-16T14:30:00Z"
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 3,
    "total_items": 15
  }
}
```

---

#### POST `/campaigns/templates`
Create a new message template.

**Request Body:**
```json
{
  "name": "Recordatorio de Cita",
  "channel": "WhatsApp",
  "category": "appointment",
  "language": "es",
  "content": "Hola {{name}}, te recordamos tu cita de mañana {{date}} a las {{time}}.",
  "variables": ["name", "date", "time"],
  "buttons": [
    {
      "type": "quick_reply",
      "text": "Confirmar"
    },
    {
      "type": "quick_reply",
      "text": "Reagendar"
    }
  ],
  "header": {
    "type": "text",
    "content": "Recordatorio"
  }
}
```

**Response (201 Created):**
```json
{
  "id": "uuid",
  "name": "Recordatorio de Cita",
  "status": "pending",
  "message": "Template created and submitted for approval",
  "created_at": "2025-11-12T11:00:00Z"
}
```

---

#### GET `/campaigns/templates/{id}`
Get template details.

**Response (200 OK):**
```json
{
  "id": "uuid",
  "name": "Confirmación de Entrevista",
  "channel": "WhatsApp",
  "category": "recruitment",
  "language": "es",
  "status": "approved",
  "content": "Hola {{name}}, te confirmamos...",
  "variables": ["name", "date", "time"],
  "usage_count": 1247,
  "last_used": "2025-11-12T10:30:00Z",
  "performance": {
    "sent": 1247,
    "delivered": 1240,
    "read": 989,
    "response_rate": 67.3
  }
}
```

---

### Campaign Scheduling

#### POST `/campaigns/{id}/schedule`
Schedule a campaign for future execution.

**Request Body:**
```json
{
  "send_at": "2025-11-15T09:00:00Z",
  "timezone": "America/Montevideo",
  "send_strategy": "immediate|throttled|optimized",
  "throttle_config": {
    "messages_per_minute": 100,
    "batch_size": 50
  },
  "retry_config": {
    "max_attempts": 3,
    "retry_delay": 300
  }
}
```

**Response (200 OK):**
```json
{
  "campaign_id": "uuid",
  "scheduled_at": "2025-11-15T09:00:00Z",
  "estimated_completion": "2025-11-15T11:30:00Z",
  "total_recipients": 1500,
  "message": "Campaign scheduled successfully"
}
```

---

#### DELETE `/campaigns/{id}/schedule`
Cancel a scheduled campaign.

**Response (200 OK):**
```json
{
  "campaign_id": "uuid",
  "status": "Draft",
  "message": "Campaign schedule cancelled"
}
```

---

### Campaign Analytics Breakdown

#### GET `/campaigns/{id}/analytics`
Get detailed analytics breakdown for a campaign.

**Query Parameters:**
- `group_by` (string): Group results by (hour|day|week|contact_type|tag)
- `start_date`, `end_date`: Date range filter

**Response (200 OK):**
```json
{
  "campaign_id": "uuid",
  "campaign_name": "Confirmacion Punta",
  "period": {
    "start": "2025-11-10T09:00:00Z",
    "end": "2025-11-10T11:30:00Z"
  },
  "overall_metrics": {
    "sent": 1247,
    "delivered": 1240,
    "failed": 7,
    "opened": 989,
    "clicked": 234,
    "replied": 567,
    "delivery_rate": 99.4,
    "open_rate": 79.7,
    "click_rate": 18.8,
    "response_rate": 45.7
  },
  "by_hour": [
    {
      "hour": "2025-11-10T09:00:00Z",
      "sent": 247,
      "delivered": 245,
      "opened": 198
    },
    {
      "hour": "2025-11-10T10:00:00Z",
      "sent": 500,
      "delivered": 498,
      "opened": 401
    }
  ],
  "by_contact_type": {
    "Lead": {
      "sent": 1100,
      "open_rate": 81.2
    },
    "Customer": {
      "sent": 147,
      "open_rate": 68.5
    }
  },
  "top_performing_messages": [
    {
      "variant": "A",
      "sent": 623,
      "open_rate": 85.2,
      "click_rate": 21.3
    },
    {
      "variant": "B",
      "sent": 624,
      "open_rate": 74.1,
      "click_rate": 16.2
    }
  ],
  "device_breakdown": {
    "mobile": 89.2,
    "desktop": 8.5,
    "tablet": 2.3
  },
  "geographic_breakdown": {
    "Montevideo": 67.3,
    "Canelones": 18.9,
    "Maldonado": 8.2,
    "Other": 5.6
  }
}
```

---

### Campaign Recipients

#### GET `/campaigns/{id}/recipients`
Get list of campaign recipients and their status.

**Query Parameters:**
- `status` (string): Filter by delivery status
- `page`, `limit`: Pagination

**Response (200 OK):**
```json
{
  "recipients": [
    {
      "contact_id": "uuid",
      "contact_name": "LUIS ZAPATA",
      "phone": "+59892637130",
      "message_id": "uuid",
      "status": "delivered",
      "sent_at": "2025-11-10T09:15:00Z",
      "delivered_at": "2025-11-10T09:15:05Z",
      "opened_at": "2025-11-10T09:47:23Z",
      "clicked_at": null,
      "replied_at": "2025-11-10T10:02:15Z"
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 25,
    "total_items": 1247
  }
}
```

---

## Tickets API - Extended

### Ticket Status Transitions

#### POST `/tickets/{id}/transition`
Change ticket status with validation of allowed transitions.

**Request Body:**
```json
{
  "status": "In Progress",
  "comment": "Started investigating the issue",
  "notify_customer": false
}
```

**Response (200 OK):**
```json
{
  "ticket_id": "uuid",
  "previous_status": "Open",
  "new_status": "In Progress",
  "transition_valid": true,
  "updated_at": "2025-11-12T11:15:00Z",
  "next_allowed_transitions": ["Resolved", "On Hold", "Open"]
}
```

**Error Response (400 Bad Request):**
```json
{
  "error": "invalid_transition",
  "message": "Cannot transition from 'Resolved' to 'Open'. Please reopen the ticket instead."
}
```

---

### SLA Management

#### GET `/tickets/{id}/sla`
Get SLA information for a ticket.

**Response (200 OK):**
```json
{
  "ticket_id": "uuid",
  "priority": "High",
  "sla_policy": {
    "name": "High Priority Support",
    "first_response_time": "15 minutes",
    "resolution_time": "4 hours"
  },
  "first_response": {
    "target": "2025-11-11T18:51:00Z",
    "actual": "2025-11-11T18:45:00Z",
    "met": true,
    "time_to_response": "9 minutes"
  },
  "resolution": {
    "target": "2025-11-11T22:36:00Z",
    "actual": null,
    "met": null,
    "time_remaining": "3h 21m",
    "breached": false
  },
  "status": "on_track|at_risk|breached"
}
```

---

#### GET `/tickets/sla/summary`
Get SLA compliance summary.

**Query Parameters:**
- `period` (string): Time period (today|week|month)
- `priority` (string): Filter by priority

**Response (200 OK):**
```json
{
  "period": "week",
  "summary": {
    "total_tickets": 67,
    "first_response_met": 62,
    "first_response_breached": 5,
    "resolution_met": 54,
    "resolution_breached": 3,
    "in_progress": 10,
    "compliance_rate": {
      "first_response": 92.5,
      "resolution": 94.7
    }
  },
  "by_priority": {
    "High": {
      "total": 15,
      "compliance_rate": 86.7
    },
    "Medium": {
      "total": 35,
      "compliance_rate": 94.3
    },
    "Low": {
      "total": 17,
      "compliance_rate": 100.0
    }
  }
}
```

---

### Ticket Assignment

#### POST `/tickets/{id}/assign`
Assign ticket to a user.

**Request Body:**
```json
{
  "user_id": "uuid",
  "notify_user": true,
  "comment": "Escalating to senior support"
}
```

**Response (200 OK):**
```json
{
  "ticket_id": "uuid",
  "assigned_to": {
    "id": "uuid",
    "name": "María García",
    "email": "maria@moiodigital.com"
  },
  "assigned_at": "2025-11-12T11:20:00Z",
  "previous_assignee": {
    "id": "uuid",
    "name": "Juan Pérez"
  }
}
```

---

#### POST `/tickets/{id}/unassign`
Unassign ticket.

**Response (200 OK):**
```json
{
  "ticket_id": "uuid",
  "assigned_to": null,
  "message": "Ticket unassigned successfully"
}
```

---

### Ticket Categories

#### GET `/tickets/categories`
Get all ticket categories.

**Response (200 OK):**
```json
{
  "categories": [
    {
      "id": "recruitment",
      "name": "Recruitment",
      "description": "Candidate and interview related issues",
      "ticket_count": 145,
      "icon": "users",
      "color": "#58a6ff"
    },
    {
      "id": "general_inquiry",
      "name": "General Inquiry",
      "description": "General questions and information requests",
      "ticket_count": 67,
      "icon": "help-circle",
      "color": "#74c365"
    },
    {
      "id": "technical",
      "name": "Technical Issue",
      "description": "System or technical problems",
      "ticket_count": 33,
      "icon": "alert-circle",
      "color": "#ff6b6b"
    }
  ]
}
```

---

### Ticket Search

#### GET `/tickets/search`
Advanced ticket search with full-text search.

**Query Parameters:**
- `q` (string): Search query
- `status`, `priority`, `category`: Filters
- `assigned_to` (string): Filter by assigned user
- `created_after`, `created_before`: Date filters
- `due_date_before`, `due_date_after`: Due date filters
- `customer_id` (string): Filter by customer
- `tags` (string): Filter by tags (comma-separated)
- `sort_by`, `order`: Sorting
- `page`, `limit`: Pagination

**Example:**
```
GET /tickets/search?q=entrevista&priority=High&status=Open&assigned_to=uuid&created_after=2025-11-01T00:00:00Z
```

**Response (200 OK):**
```json
{
  "tickets": [...],
  "search_metadata": {
    "query": "entrevista",
    "filters_applied": ["priority", "status", "assigned_to", "created_after"],
    "total_results": 12,
    "search_time_ms": 45
  },
  "pagination": {...}
}
```

---

## Flows API - Extended

### Trigger Types & Schemas

#### GET `/flows/triggers`
Get all available trigger types and their schemas.

**Response (200 OK):**
```json
{
  "triggers": [
    {
      "type": "contact_created",
      "name": "Contact Created",
      "description": "Triggered when a new contact is created",
      "category": "contacts",
      "schema": {
        "conditions": {
          "type": "object",
          "properties": {
            "contact_type": {
              "type": "string",
              "enum": ["Lead", "Customer", "Partner", "Vendor"]
            },
            "tags": {
              "type": "array",
              "items": {"type": "string"}
            },
            "source": {"type": "string"}
          }
        }
      },
      "payload_example": {
        "contact_id": "uuid",
        "contact_name": "LUIS ZAPATA",
        "contact_type": "Lead",
        "tags": ["website"],
        "created_at": "2025-11-12T11:25:00Z"
      }
    },
    {
      "type": "message_received",
      "name": "Message Received",
      "description": "Triggered when a message is received from a contact",
      "category": "communications",
      "schema": {
        "conditions": {
          "type": "object",
          "properties": {
            "channel": {
              "type": "string",
              "enum": ["WhatsApp", "Email", "SMS"]
            },
            "message_contains": {"type": "string"},
            "contact_tags": {
              "type": "array",
              "items": {"type": "string"}
            }
          }
        }
      },
      "payload_example": {
        "message_id": "uuid",
        "conversation_id": "uuid",
        "contact_id": "uuid",
        "channel": "WhatsApp",
        "content": "Hola, quiero confirmar mi entrevista",
        "timestamp": "2025-11-12T11:25:00Z"
      }
    },
    {
      "type": "ticket_created",
      "name": "Ticket Created",
      "description": "Triggered when a new ticket is created",
      "category": "tickets",
      "schema": {
        "conditions": {
          "type": "object",
          "properties": {
            "priority": {
              "type": "string",
              "enum": ["High", "Medium", "Low"]
            },
            "category": {"type": "string"}
          }
        }
      }
    },
    {
      "type": "campaign_response",
      "name": "Campaign Response",
      "description": "Triggered when a contact responds to a campaign",
      "category": "campaigns",
      "schema": {
        "conditions": {
          "type": "object",
          "properties": {
            "campaign_id": {"type": "string"},
            "response_type": {
              "type": "string",
              "enum": ["positive", "negative", "neutral"]
            }
          }
        }
      }
    },
    {
      "type": "schedule",
      "name": "Scheduled Trigger",
      "description": "Triggered on a schedule (cron expression)",
      "category": "utility",
      "schema": {
        "conditions": {
          "type": "object",
          "properties": {
            "cron": {
              "type": "string",
              "description": "Cron expression (e.g., '0 9 * * MON' for every Monday at 9am)"
            }
          },
          "required": ["cron"]
        }
      }
    }
  ]
}
```

---

### Action Types & Schemas

#### GET `/flows/actions`
Get all available action types and their schemas.

**Response (200 OK):**
```json
{
  "actions": [
    {
      "type": "send_message",
      "name": "Send Message",
      "description": "Send a message via specified channel",
      "category": "communications",
      "schema": {
        "config": {
          "type": "object",
          "properties": {
            "channel": {
              "type": "string",
              "enum": ["WhatsApp", "Email", "SMS"],
              "required": true
            },
            "template_id": {"type": "string"},
            "message": {"type": "string"},
            "variables": {
              "type": "object",
              "description": "Template variables (e.g., {\"name\": \"{{contact.name}}\"}"
            }
          }
        }
      },
      "config_example": {
        "channel": "WhatsApp",
        "template_id": "uuid",
        "variables": {
          "name": "{{contact.name}}",
          "date": "{{trigger.date}}"
        }
      }
    },
    {
      "type": "create_ticket",
      "name": "Create Ticket",
      "description": "Create a support ticket",
      "category": "tickets",
      "schema": {
        "config": {
          "type": "object",
          "properties": {
            "subject": {"type": "string", "required": true},
            "description": {"type": "string"},
            "priority": {
              "type": "string",
              "enum": ["High", "Medium", "Low"]
            },
            "category": {"type": "string"},
            "assign_to": {"type": "string"}
          }
        }
      }
    },
    {
      "type": "add_tag",
      "name": "Add Tag",
      "description": "Add tags to contact",
      "category": "contacts",
      "schema": {
        "config": {
          "type": "object",
          "properties": {
            "tags": {
              "type": "array",
              "items": {"type": "string"},
              "required": true
            }
          }
        }
      }
    },
    {
      "type": "remove_tag",
      "name": "Remove Tag",
      "description": "Remove tags from contact",
      "category": "contacts"
    },
    {
      "type": "update_contact",
      "name": "Update Contact",
      "description": "Update contact fields",
      "category": "contacts",
      "schema": {
        "config": {
          "type": "object",
          "properties": {
            "fields": {
              "type": "object",
              "description": "Field updates (e.g., {\"type\": \"Customer\", \"company\": \"New Co\"})"
            }
          }
        }
      }
    },
    {
      "type": "delay",
      "name": "Delay",
      "description": "Wait for specified duration",
      "category": "utility",
      "schema": {
        "config": {
          "type": "object",
          "properties": {
            "duration": {"type": "integer", "required": true},
            "unit": {
              "type": "string",
              "enum": ["seconds", "minutes", "hours", "days"],
              "required": true
            }
          }
        }
      }
    },
    {
      "type": "conditional",
      "name": "Conditional Branch",
      "description": "Execute different actions based on condition",
      "category": "logic",
      "schema": {
        "config": {
          "type": "object",
          "properties": {
            "condition": {
              "type": "string",
              "description": "Condition expression (e.g., 'contact.tags contains \"vip\"')",
              "required": true
            },
            "if_true": {
              "type": "array",
              "items": {"type": "string"},
              "description": "Action IDs to execute if true"
            },
            "if_false": {
              "type": "array",
              "items": {"type": "string"},
              "description": "Action IDs to execute if false"
            }
          }
        }
      }
    },
    {
      "type": "http_request",
      "name": "HTTP Request",
      "description": "Make HTTP request to external API",
      "category": "integration",
      "schema": {
        "config": {
          "type": "object",
          "properties": {
            "method": {
              "type": "string",
              "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]
            },
            "url": {"type": "string", "required": true},
            "headers": {"type": "object"},
            "body": {"type": "object"}
          }
        }
      }
    }
  ]
}
```

---

### Flow Versioning

#### GET `/flows/{id}/versions`
Get version history of a flow.

**Response (200 OK):**
```json
{
  "flow_id": "uuid",
  "current_version": 3,
  "versions": [
    {
      "version": 3,
      "status": "Active",
      "created_at": "2025-11-12T10:00:00Z",
      "created_by": {
        "id": "uuid",
        "name": "María García"
      },
      "changes": "Added conditional branch for VIP contacts",
      "is_current": true
    },
    {
      "version": 2,
      "status": "Archived",
      "created_at": "2025-11-05T14:30:00Z",
      "created_by": {
        "id": "uuid",
        "name": "Admin User"
      },
      "changes": "Updated message template",
      "is_current": false
    },
    {
      "version": 1,
      "status": "Archived",
      "created_at": "2025-10-01T10:00:00Z",
      "created_by": {
        "id": "uuid",
        "name": "Admin User"
      },
      "changes": "Initial version",
      "is_current": false
    }
  ]
}
```

---

#### POST `/flows/{id}/versions/{version}/restore`
Restore a previous version of a flow.

**Response (200 OK):**
```json
{
  "flow_id": "uuid",
  "restored_version": 2,
  "new_current_version": 4,
  "message": "Flow version 2 restored as version 4"
}
```

---

### Flow Testing

#### POST `/flows/{id}/test`
Test flow execution without actually performing actions.

**Request Body:**
```json
{
  "trigger_data": {
    "contact_id": "uuid",
    "contact_name": "Test Contact",
    "contact_type": "Lead"
  },
  "dry_run": true
}
```

**Response (200 OK):**
```json
{
  "test_id": "uuid",
  "flow_id": "uuid",
  "status": "success",
  "duration": "2.3s",
  "actions_simulated": 5,
  "results": [
    {
      "action_id": "action-1",
      "type": "send_message",
      "status": "would_send",
      "simulated_result": {
        "message": "Would send WhatsApp message to +59892637130",
        "content": "Bienvenido Test Contact!"
      }
    },
    {
      "action_id": "action-2",
      "type": "delay",
      "status": "would_wait",
      "simulated_result": {
        "duration": "86400 seconds (1 day)"
      }
    },
    {
      "action_id": "action-3",
      "type": "conditional",
      "status": "evaluated",
      "simulated_result": {
        "condition": "contact.tags contains 'interested'",
        "result": false,
        "branch_taken": "if_false"
      }
    }
  ],
  "warnings": [],
  "errors": []
}
```

---

## Complete Data Model Definitions

### User Model
```typescript
{
  id: string (UUID, primary key)
  username: string (required, unique, min: 3, max: 50)
  email: string (required, unique, email format)
  password: string (hashed, bcrypt, required)
  full_name: string (required, max: 100)
  role: "admin" | "manager" | "agent" | "user" (required, default: "user")
  status: "active" | "inactive" | "suspended" (required, default: "active")
  avatar_url: string | null (URL format)
  phone: string | null (E.164 format)
  permissions: string[] (array of permission codes)
  organization_id: string (UUID, foreign key, required)
  last_login: ISO 8601 timestamp | null
  created_at: ISO 8601 timestamp (auto-generated)
  updated_at: ISO 8601 timestamp (auto-updated)
}
```

**Indexes:**
- `username` (unique)
- `email` (unique)
- `organization_id`
- `role`
- `status`

**Relationships:**
- `organization_id` → Organization (many-to-one)

---

### Organization Model
```typescript
{
  id: string (UUID, primary key)
  name: string (required, max: 200)
  slug: string (required, unique, lowercase, alphanumeric + hyphens)
  industry: string | null (max: 100)
  logo_url: string | null (URL format)
  timezone: string (required, IANA timezone, default: "America/Montevideo")
  locale: string (required, default: "es_UY")
  currency: string (required, ISO 4217, default: "UYU")
  date_format: string (required, default: "DD/MM/YYYY")
  time_format: "12h" | "24h" (required, default: "24h")
  business_hours: Record<string, {start: string, end: string} | null>
  contact_info: {
    email: string | null
    phone: string | null
    address: string | null
  }
  subscription: {
    plan: "free" | "professional" | "enterprise"
    status: "active" | "trial" | "cancelled"
    expires_at: ISO 8601 timestamp | null
  }
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
}
```

**Indexes:**
- `slug` (unique)

---

### Contact Model (Extended)
```typescript
{
  id: string (UUID, primary key)
  name: string (required, max: 200)
  email: string | null (email format, unique if not null)
  phone: string | null (E.164 format)
  company: string | null (max: 200)
  type: "Lead" | "Customer" | "Partner" | "Vendor" (required, default: "Lead")
  status: "active" | "inactive" | "blocked" (required, default: "active")
  source: string | null (e.g., "Website", "Referral", "Campaign", max: 100)
  tags: string[] (array of tag strings)
  custom_fields: Record<string, any> (JSONB)
  address: {
    street: string | null
    city: string | null
    state: string | null
    country: string | null
    postal_code: string | null
  } | null
  social_profiles: {
    linkedin: string | null
    twitter: string | null
    instagram: string | null
    facebook: string | null
  } | null
  organization_id: string (UUID, foreign key, required)
  created_by: string (UUID, foreign key to User) | null
  assigned_to: string (UUID, foreign key to User) | null
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
  last_contact_at: ISO 8601 timestamp | null
}
```

**Indexes:**
- `email` (unique, sparse)
- `phone` (sparse)
- `organization_id`
- `type`
- `status`
- `tags` (GIN index for array)
- `created_at`
- `last_contact_at`

**Relationships:**
- `organization_id` → Organization (many-to-one)
- `created_by` → User (many-to-one)
- `assigned_to` → User (many-to-one)

---

### Deal Model (Complete)
```typescript
{
  id: string (UUID, primary key)
  title: string (required, max: 200)
  description: string | null (text)
  contact_id: string (UUID, foreign key, required)
  organization_id: string (UUID, foreign key, required)
  value: number (required, decimal, precision: 12, scale: 2)
  currency: string (required, ISO 4217, default: "USD")
  stage: "qualified" | "proposal" | "negotiation" | "closed" | "lost" (required, default: "qualified")
  probability: number (0-100, default based on stage)
  expected_close_date: ISO 8601 date | null
  actual_close_date: ISO 8601 date | null
  lost_reason: string | null (max: 500)
  assigned_to: string (UUID, foreign key to User) | null
  created_by: string (UUID, foreign key to User) | null
  tags: string[]
  custom_fields: Record<string, any> (JSONB)
  products: Array<{
    product_id: string
    product_name: string
    quantity: number
    unit_price: number
    total: number
  }>
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
  closed_at: ISO 8601 timestamp | null
}
```

**Indexes:**
- `contact_id`
- `organization_id`
- `stage`
- `assigned_to`
- `expected_close_date`
- `created_at`

**Relationships:**
- `contact_id` → Contact (many-to-one)
- `organization_id` → Organization (many-to-one)
- `assigned_to` → User (many-to-one)
- `created_by` → User (many-to-one)

---

### Conversation Model (Complete)
```typescript
{
  id: string (UUID, primary key)
  contact_id: string (UUID, foreign key, required)
  organization_id: string (UUID, foreign key, required)
  channel: "WhatsApp" | "Email" | "SMS" | "Instagram" | "Telegram" | "Facebook" (required)
  channel_account_id: string | null (external channel account identifier)
  status: "active" | "archived" | "closed" (required, default: "active")
  assigned_to: string (UUID, foreign key to User) | null
  unread_count: number (default: 0, min: 0)
  last_message_at: ISO 8601 timestamp | null
  last_message_preview: string | null (max: 200)
  tags: string[]
  metadata: Record<string, any> (JSONB, channel-specific data)
  ai_summary: string | null (AI-generated conversation summary)
  sentiment: "positive" | "neutral" | "negative" | null
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
}
```

**Indexes:**
- `contact_id`
- `organization_id`
- `channel`
- `status`
- `assigned_to`
- `last_message_at`
- `unread_count` (where > 0)

**Relationships:**
- `contact_id` → Contact (many-to-one)
- `organization_id` → Organization (many-to-one)
- `assigned_to` → User (many-to-one)

---

### Message Model (Complete)
```typescript
{
  id: string (UUID, primary key)
  conversation_id: string (UUID, foreign key, required)
  external_id: string | null (channel-specific message ID)
  content: string (required, max: 4096)
  sender: "agent" | "contact" | "system" (required)
  sender_id: string (UUID, foreign key to User) | null
  sender_name: string | null (max: 200)
  type: "text" | "image" | "video" | "audio" | "document" | "location" | "system_note" (required, default: "text")
  status: "queued" | "sent" | "delivered" | "read" | "failed" (required, default: "queued")
  error_message: string | null (max: 500)
  attachments: Array<{
    id: string
    type: "image" | "video" | "audio" | "document"
    url: string
    filename: string
    mime_type: string
    size: number (bytes)
  }>
  metadata: Record<string, any> (JSONB)
  timestamp: ISO 8601 timestamp (required)
  queued_at: ISO 8601 timestamp | null
  sent_at: ISO 8601 timestamp | null
  delivered_at: ISO 8601 timestamp | null
  read_at: ISO 8601 timestamp | null
  failed_at: ISO 8601 timestamp | null
  created_at: ISO 8601 timestamp
}
```

**Indexes:**
- `conversation_id`
- `external_id` (unique, sparse)
- `sender`
- `status`
- `timestamp`
- `created_at`

**Relationships:**
- `conversation_id` → Conversation (many-to-one)
- `sender_id` → User (many-to-one, nullable)

---

### Campaign Model (Complete)
```typescript
{
  id: string (UUID, primary key)
  name: string (required, max: 200)
  type: string (required, e.g., "Express Campaign", "Drip Campaign", max: 100)
  description: string | null (text)
  organization_id: string (UUID, foreign key, required)
  status: "Draft" | "Scheduled" | "Running" | "Paused" | "Completed" | "Cancelled" (required, default: "Draft")
  channel: "WhatsApp" | "Email" | "SMS" (required)
  template_id: string (UUID, foreign key) | null
  target_audience: {
    contact_filter: Record<string, any> (filter conditions)
    segment_ids: string[] | null (array of segment UUIDs)
    contact_ids: string[] | null (explicit contact list)
    estimated_count: number | null
  }
  schedule: {
    send_at: ISO 8601 timestamp | null
    timezone: string (IANA timezone)
    send_strategy: "immediate" | "throttled" | "optimized" (default: "immediate")
    throttle_config: {
      messages_per_minute: number | null
      batch_size: number | null
    } | null
  }
  content: {
    message: string | null
    variables: Record<string, string>
    subject: string | null (for Email)
  }
  metrics: {
    sent: number (default: 0)
    delivered: number (default: 0)
    failed: number (default: 0)
    opened: number (default: 0)
    clicked: number (default: 0)
    replied: number (default: 0)
    unsubscribed: number (default: 0)
  }
  created_by: string (UUID, foreign key to User) | null
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
  scheduled_at: ISO 8601 timestamp | null
  started_at: ISO 8601 timestamp | null
  completed_at: ISO 8601 timestamp | null
}
```

**Indexes:**
- `organization_id`
- `status`
- `channel`
- `template_id`
- `created_by`
- `scheduled_at`
- `started_at`

**Relationships:**
- `organization_id` → Organization (many-to-one)
- `template_id` → MessageTemplate (many-to-one)
- `created_by` → User (many-to-one)

---

### MessageTemplate Model
```typescript
{
  id: string (UUID, primary key)
  name: string (required, max: 200)
  organization_id: string (UUID, foreign key, required)
  channel: "WhatsApp" | "Email" | "SMS" (required)
  category: string | null (e.g., "recruitment", "appointment", max: 100)
  language: string (required, ISO 639-1, default: "es")
  status: "draft" | "pending" | "approved" | "rejected" (required, default: "draft")
  rejection_reason: string | null (max: 500)
  content: string (required, text, supports {{variable}} placeholders)
  variables: string[] (array of variable names used in content)
  header: {
    type: "text" | "image" | "video" | "document" | null
    content: string | null
  } | null
  footer: {
    content: string | null (max: 60)
  } | null
  buttons: Array<{
    type: "quick_reply" | "call_to_action" | "url"
    text: string (max: 20)
    url: string | null (for url buttons)
    phone_number: string | null (for call buttons)
  }> | null
  external_id: string | null (channel provider's template ID)
  usage_count: number (default: 0)
  created_by: string (UUID, foreign key to User) | null
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
  approved_at: ISO 8601 timestamp | null
  last_used_at: ISO 8601 timestamp | null
}
```

**Indexes:**
- `organization_id`
- `channel`
- `category`
- `status`
- `external_id` (unique, sparse)

**Relationships:**
- `organization_id` → Organization (many-to-one)
- `created_by` → User (many-to-one)

---

### Ticket Model (Complete)
```typescript
{
  id: string (UUID, primary key)
  ticket_number: string (required, unique, auto-generated, format: "TICK-YYYY-NNNN")
  subject: string (required, max: 500)
  description: string | null (text)
  customer_id: string (UUID, foreign key to Contact, required)
  organization_id: string (UUID, foreign key, required)
  status: "Open" | "In Progress" | "On Hold" | "Resolved" | "Closed" | "Cancelled" (required, default: "Open")
  priority: "Critical" | "High" | "Medium" | "Low" (required, default: "Medium")
  category: string | null (max: 100)
  sub_category: string | null (max: 100)
  assigned_to: string (UUID, foreign key to User) | null
  created_by: string (UUID, foreign key to User) | null
  due_date: ISO 8601 timestamp | null
  tags: string[]
  custom_fields: Record<string, any> (JSONB)
  sla_policy_id: string (UUID) | null
  first_response_at: ISO 8601 timestamp | null
  first_response_due: ISO 8601 timestamp | null
  resolution_due: ISO 8601 timestamp | null
  resolved_at: ISO 8601 timestamp | null
  closed_at: ISO 8601 timestamp | null
  resolution_time_minutes: number | null
  satisfaction_rating: 1 | 2 | 3 | 4 | 5 | null
  satisfaction_comment: string | null (max: 1000)
  related_conversation_id: string (UUID) | null
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
}
```

**Indexes:**
- `ticket_number` (unique)
- `customer_id`
- `organization_id`
- `status`
- `priority`
- `category`
- `assigned_to`
- `due_date`
- `created_at`

**Relationships:**
- `customer_id` → Contact (many-to-one)
- `organization_id` → Organization (many-to-one)
- `assigned_to` → User (many-to-one)
- `created_by` → User (many-to-one)

---

### TicketComment Model
```typescript
{
  id: string (UUID, primary key)
  ticket_id: string (UUID, foreign key, required)
  author_id: string (UUID, foreign key to User) | null
  author_name: string | null (for system/automated comments, max: 200)
  content: string (required, text)
  type: "comment" | "status_change" | "assignment" | "system_note" (required, default: "comment")
  internal: boolean (default: false, if true, not visible to customer)
  attachments: Array<{
    id: string
    type: "file" | "image"
    url: string
    filename: string
    mime_type: string
    size: number
  }>
  created_at: ISO 8601 timestamp
}
```

**Indexes:**
- `ticket_id`
- `author_id`
- `created_at`

**Relationships:**
- `ticket_id` → Ticket (many-to-one)
- `author_id` → User (many-to-one)

---

### Workflow (Flow) Model (Complete)
```typescript
{
  id: string (UUID, primary key)
  name: string (required, max: 200)
  description: string | null (text)
  organization_id: string (UUID, foreign key, required)
  status: "Draft" | "Testing" | "Active" | "Disabled" (required, default: "Draft")
  version: number (required, default: 1, auto-increment)
  trigger: {
    type: string (required, e.g., "contact_created", "message_received")
    conditions: Record<string, any> (JSONB)
  }
  actions: Array<WorkflowAction>
  execution_count: number (default: 0)
  success_count: number (default: 0)
  failure_count: number (default: 0)
  last_execution_at: ISO 8601 timestamp | null
  created_by: string (UUID, foreign key to User) | null
  created_at: ISO 8601 timestamp
  updated_at: ISO 8601 timestamp
  activated_at: ISO 8601 timestamp | null
}
```

**WorkflowAction Type:**
```typescript
{
  id: string (unique within workflow)
  type: string (e.g., "send_message", "create_ticket", "delay", "conditional")
  config: Record<string, any> (JSONB, action-specific configuration)
  position: number (execution order, starting from 1)
  depends_on: string[] | null (array of action IDs that must complete first)
}
```

**Indexes:**
- `organization_id`
- `status`
- `trigger.type` (JSONB index)
- `created_by`
- `version`

**Relationships:**
- `organization_id` → Organization (many-to-one)
- `created_by` → User (many-to-one)

---

### WorkflowExecution Model
```typescript
{
  id: string (UUID, primary key)
  workflow_id: string (UUID, foreign key, required)
  workflow_version: number (workflow version at time of execution)
  status: "pending" | "running" | "success" | "failed" | "cancelled" (required, default: "pending")
  trigger_data: Record<string, any> (JSONB, data that triggered the workflow)
  context: Record<string, any> (JSONB, execution context and variables)
  actions_completed: number (default: 0)
  actions_failed: number (default: 0)
  current_action_id: string | null
  error_message: string | null (text)
  logs: Array<{
    action_id: string
    action_type: string
    status: "pending" | "running" | "success" | "failed" | "skipped"
    timestamp: ISO 8601 timestamp
    message: string | null
    data: Record<string, any> | null
  }>
  started_at: ISO 8601 timestamp | null
  completed_at: ISO 8601 timestamp | null
  duration_ms: number | null
  created_at: ISO 8601 timestamp
}
```

**Indexes:**
- `workflow_id`
- `status`
- `started_at`
- `created_at`

**Relationships:**
- `workflow_id` → Workflow (many-to-one)

---

## Webhook Event Schemas

### Webhook Configuration

**Webhook Registration Endpoint:**
```
POST /webhooks/register
```

**Request Body:**
```json
{
  "url": "https://your-ai-agent.com/webhook",
  "events": [
    "message.received",
    "ticket.created",
    "contact.created",
    "campaign.completed"
  ],
  "secret": "webhook_secret_key_for_signature_verification",
  "active": true
}
```

---

### Event: message.received

**Payload:**
```json
{
  "event": "message.received",
  "event_id": "uuid",
  "timestamp": "2025-11-12T11:30:00Z",
  "organization_id": "uuid",
  "data": {
    "message_id": "uuid",
    "conversation_id": "uuid",
    "contact": {
      "id": "uuid",
      "name": "LUIS ZAPATA",
      "email": "luis@example.com",
      "phone": "+59892637130",
      "type": "Lead",
      "tags": ["priority"]
    },
    "message": {
      "content": "Hola, quiero confirmar mi entrevista para mañana",
      "type": "text",
      "channel": "WhatsApp",
      "attachments": [],
      "timestamp": "2025-11-12T11:30:00Z"
    },
    "conversation_context": {
      "previous_messages_count": 5,
      "ai_summary": "Contact is interested in job interview",
      "sentiment": "positive"
    }
  }
}
```

**Expected Response:**
```json
{
  "processed": true,
  "actions": [
    {
      "type": "send_reply",
      "message": "Perfecto Luis! Tu entrevista está confirmada para mañana.",
      "mark_as_read": true
    },
    {
      "type": "add_tag",
      "tags": ["confirmed"]
    }
  ]
}
```

---

### Event: ticket.created

**Payload:**
```json
{
  "event": "ticket.created",
  "event_id": "uuid",
  "timestamp": "2025-11-12T11:32:00Z",
  "organization_id": "uuid",
  "data": {
    "ticket": {
      "id": "uuid",
      "ticket_number": "TICK-2025-247",
      "subject": "Consulta sobre cambio de horario",
      "description": "El candidato solicita modificar horario de entrevista",
      "priority": "Medium",
      "category": "scheduling",
      "status": "Open"
    },
    "customer": {
      "id": "uuid",
      "name": "MARÍA GONZÁLEZ",
      "email": "maria@example.com",
      "phone": "+59899999999"
    },
    "created_by": {
      "id": "uuid",
      "name": "Sistema Automatizado",
      "type": "system"
    }
  }
}
```

---

### Event: contact.created

**Payload:**
```json
{
  "event": "contact.created",
  "event_id": "uuid",
  "timestamp": "2025-11-12T11:35:00Z",
  "organization_id": "uuid",
  "data": {
    "contact": {
      "id": "uuid",
      "name": "CARLOS RODRIGUEZ",
      "email": "carlos@example.com",
      "phone": "+59888888888",
      "type": "Lead",
      "source": "Website Form",
      "tags": ["website", "new"]
    },
    "created_by": {
      "id": null,
      "name": "Website Integration",
      "type": "integration"
    }
  }
}
```

---

### Event: campaign.completed

**Payload:**
```json
{
  "event": "campaign.completed",
  "event_id": "uuid",
  "timestamp": "2025-11-12T11:40:00Z",
  "organization_id": "uuid",
  "data": {
    "campaign": {
      "id": "uuid",
      "name": "Confirmacion Punta Y Alrededores",
      "type": "Express Campaign",
      "channel": "WhatsApp"
    },
    "metrics": {
      "sent": 1247,
      "delivered": 1240,
      "failed": 7,
      "opened": 989,
      "clicked": 234,
      "replied": 567,
      "delivery_rate": 99.4,
      "open_rate": 79.7,
      "click_rate": 18.8,
      "response_rate": 45.7
    },
    "duration": {
      "started_at": "2025-11-10T09:00:00Z",
      "completed_at": "2025-11-10T11:30:00Z",
      "duration_minutes": 150
    }
  }
}
```

---

### Webhook Security

**Signature Verification:**

All webhooks include an `X-Moio-Signature` header:

```
X-Moio-Signature: sha256=<HMAC_SHA256_signature>
```

**Verify signature in your webhook handler:**
```python
import hmac
import hashlib

def verify_webhook_signature(payload_body, signature_header, secret):
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(
        f"sha256={expected_signature}",
        signature_header
    )
```

---

### Webhook Retry Policy

- **Retry attempts:** 3
- **Retry delay:** Exponential backoff (30s, 60s, 120s)
- **Timeout:** 30 seconds per attempt
- **Success criteria:** HTTP 200-299 response
- **Failure handling:** After 3 failed attempts, webhook is marked as failed and admin is notified

---

## Technical Specifications - Extended

### Pagination Format (Standardized)

All paginated endpoints return this consistent format:

```json
{
  "data": [...],
  "pagination": {
    "current_page": 1,
    "total_pages": 10,
    "total_items": 500,
    "items_per_page": 50,
    "has_next": true,
    "has_previous": false,
    "next_page_url": "https://api.moiodigital.com/v1/contacts?page=2&limit=50",
    "previous_page_url": null
  }
}
```

**Query Parameters:**
- `page`: Page number (integer, min: 1, default: 1)
- `limit`: Items per page (integer, min: 1, max: 100, default: 50)

---

### Error Response Format (Complete)

**Standard Error Structure:**
```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "details": {
    "field_name": ["Error message 1", "Error message 2"]
  },
  "request_id": "uuid",
  "timestamp": "2025-11-12T11:45:00Z",
  "path": "/v1/contacts",
  "method": "POST"
}
```

**Common Error Codes:**

**400 Bad Request:**
```json
{
  "error": "bad_request",
  "message": "Invalid request parameters",
  "details": {
    "limit": ["Must be between 1 and 100"]
  }
}
```

**422 Validation Error:**
```json
{
  "error": "validation_error",
  "message": "Validation failed",
  "details": {
    "email": ["Invalid email format"],
    "phone": ["Phone number must be in E.164 format"],
    "name": ["Name is required"]
  }
}
```

**409 Conflict:**
```json
{
  "error": "conflict",
  "message": "Resource already exists",
  "details": {
    "email": ["Contact with this email already exists"]
  }
}
```

---

### Rate Limiting (Detailed)

**Rate Limit Tiers:**

1. **Standard Tier** (Free/Basic plans):
   - 1,000 requests/hour per user
   - 10,000 requests/day per organization

2. **Professional Tier**:
   - 5,000 requests/hour per user
   - 50,000 requests/day per organization

3. **Enterprise Tier**:
   - 10,000 requests/hour per user
   - Unlimited daily requests

**Special Limits:**
- Bulk operations: 100 requests/hour
- File uploads: 1,000 files/day
- Webhook deliveries: 50,000/hour

**Headers:**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1699876543
X-RateLimit-Retry-After: 3600
```

**Rate Limit Exceeded (429):**
```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Please try again later.",
  "retry_after": 3600,
  "limit": 1000,
  "reset_at": "2025-11-12T13:00:00Z"
}
```

---

### Field Validation Rules

**Common Validations:**

- `email`: RFC 5322 format, max 254 characters
- `phone`: E.164 format (e.g., +59892637130)
- `url`: Valid HTTP/HTTPS URL, max 2048 characters
- `uuid`: Valid UUID v4 format
- `iso_timestamp`: ISO 8601 format
- `currency`: ISO 4217 3-letter code
- `timezone`: IANA timezone database name
- `language`: ISO 639-1 2-letter code

**String Lengths:**
- Short strings (names, titles): max 200 characters
- Medium strings (descriptions): max 500 characters
- Long strings (content, messages): max 4096 characters
- Text fields: unlimited (stored as TEXT in database)

**Numeric Ranges:**
- Percentages: 0-100
- Probabilities: 0-100
- Ratings: 1-5
- Currency amounts: precision 12, scale 2 (max: 9,999,999,999.99)

---

### Enum Values

**Contact Types:**
```
Lead | Customer | Partner | Vendor
```

**Contact Status:**
```
active | inactive | blocked
```

**Deal Stages:**
```
qualified | proposal | negotiation | closed | lost
```

**Ticket Status:**
```
Open | In Progress | On Hold | Resolved | Closed | Cancelled
```

**Ticket Priority:**
```
Critical | High | Medium | Low
```

**Message Status:**
```
queued | sent | delivered | read | failed
```

**Campaign Status:**
```
Draft | Scheduled | Running | Paused | Completed | Cancelled
```

**Workflow Status:**
```
Draft | Testing | Active | Disabled
```

**User Roles:**
```
admin | manager | agent | user
```

**User Status:**
```
active | inactive | suspended
```

**Channel Types:**
```
WhatsApp | Email | SMS | Instagram | Telegram | Facebook
```

---

This completes the additional API specifications. These should be integrated into the main documentation.
