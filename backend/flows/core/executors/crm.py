"""
CRM Executors - Contact, Ticket, and Candidate Celery Tasks

Standalone Celery tasks for CRM operations that can be:
1. Called directly from anywhere (webhooks, views, scripts)
2. Registered as flow node executors

All tasks return structured ExecutorResult for downstream chaining.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from celery import shared_task

from moio_platform.settings import FLOWS_Q

from .base import (
    ExecutorResult,
    ExecutorContext,
    create_result,
    create_error_result,
    get_tenant_config,
    log_entry,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="executors.create_contact", queue=FLOWS_Q)
def create_contact_task(
    self,
    tenant_id: str,
    fullname: str,
    phone: str,
    email: Optional[str] = None,
    whatsapp_name: Optional[str] = None,
    source: Optional[str] = None,
    contact_type_id: Optional[str] = None,
    contact_type_name: Optional[str] = None,
    custom_fields: Optional[Dict[str, Any]] = None,
    sandbox: bool = False,
) -> Dict[str, Any]:
    """
    Create or update a contact in the CRM.
    
    Args:
        tenant_id: Tenant ID for configuration lookup
        fullname: Contact's full name
        phone: Contact's phone number (required)
        email: Contact's email address
        whatsapp_name: WhatsApp display name
        source: Source of the contact (e.g., 'flow', 'webhook', 'campaign')
        contact_type_id: Contact type ID (pk)
        contact_type_name: Contact type name (alternative to ID)
        custom_fields: Additional custom field data
        sandbox: If True, skip actual creation and return simulated result
    
    Returns:
        ExecutorResult dict with:
        - success: bool
        - data: {contact_id, fullname, phone, email, ...}
        - logs: execution logs
        - error: error message if failed
        - metadata: timing info
    """
    with ExecutorContext("create_contact", self.request.id, sandbox=sandbox) as ctx:
        result = ctx.result
        
        if ctx.sandbox:
            return ctx.sandbox_skip(
                f"Create contact: {fullname} ({phone})",
                {
                    "contact_id": "sandbox-contact-001",
                    "fullname": fullname,
                    "phone": phone,
                    "email": email or "",
                    "message": "Contact created (simulated)",
                }
            )
        
        tenant, config = get_tenant_config(tenant_id)
        if not tenant:
            result.success = False
            result.error = f"Tenant not found: {tenant_id}"
            result.error_log(result.error)
            return result.to_dict()
        
        result.info(f"Creating contact: {fullname}", {"phone": phone, "email": email})
        
        try:
            from crm.services.contact_service import ContactService
            
            contact, message = ContactService.create_contact(
                tenant=tenant,
                fullname=fullname,
                email=email or "",
                phone=phone,
                whatsapp_name=whatsapp_name or "",
                source=source or "flow",
                ctype_name=contact_type_name,
                ctype_pk=contact_type_id,
            )
            
            if contact:
                result.success = True
                result.data = {
                    "contact_id": str(contact.id) if hasattr(contact, 'id') else str(contact.user_id),
                    "fullname": contact.fullname,
                    "phone": contact.phone,
                    "email": contact.email,
                    "message": message,
                }
                result.info(f"Contact created: {contact.id if hasattr(contact, 'id') else contact.user_id}")
            else:
                result.success = False
                result.error = message
                result.error_log(message)
                
        except Exception as e:
            result.success = False
            result.error = f"Failed to create contact: {e}"
            result.error_log(result.error)
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.upsert_contact", queue=FLOWS_Q)
def upsert_contact_task(
    self,
    tenant_id: str,
    fullname: str,
    phone: str,
    contact_type_id: str,
) -> Dict[str, Any]:
    """
    Upsert (create or update) a contact by phone number.
    
    If a contact with the given phone exists, returns it.
    Otherwise, creates a new contact.
    
    Args:
        tenant_id: Tenant ID for configuration lookup
        fullname: Contact's full name
        phone: Contact's phone number (used for lookup)
        contact_type_id: Contact type ID (required)
    
    Returns:
        ExecutorResult dict with contact details
    """
    with ExecutorContext("upsert_contact", self.request.id) as ctx:
        result = ctx.result
        
        tenant, config = get_tenant_config(tenant_id)
        if not tenant:
            result.success = False
            result.error = f"Tenant not found: {tenant_id}"
            result.error_log(result.error)
            return result.to_dict()
        
        result.info(f"Upserting contact: {fullname}", {"phone": phone})
        
        try:
            from crm.services.contact_service import ContactService
            
            contact = ContactService.contact_upsert(
                tenant=tenant,
                fullname=fullname,
                phone=phone,
                ctype_pk=contact_type_id,
            )
            
            result.success = True
            result.data = {
                "contact_id": str(contact.id) if hasattr(contact, 'id') else str(contact.user_id),
                "fullname": contact.fullname,
                "phone": contact.phone,
                "email": contact.email or "",
                "is_new": False,
            }
            result.info(f"Contact upserted: {result.data['contact_id']}")
                
        except ValueError as e:
            result.success = False
            result.error = str(e)
            result.error_log(result.error)
        except Exception as e:
            result.success = False
            result.error = f"Failed to upsert contact: {e}"
            result.error_log(result.error)
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.create_ticket", queue=FLOWS_Q)
def create_ticket_task(
    self,
    tenant_id: str,
    contact_id: str,
    service: str,
    description: str,
    origin_session_id: Optional[str] = None,
    sandbox: bool = False,
) -> Dict[str, Any]:
    """
    Create a support ticket in the CRM.
    
    Args:
        tenant_id: Tenant ID
        contact_id: Contact ID (user_id) associated with the ticket
        service: Service category for the ticket
        description: Ticket description
        origin_session_id: Optional chatbot session ID for tracking
        sandbox: If True, skip actual creation and return simulated result
    
    Returns:
        ExecutorResult dict with:
        - success: bool
        - data: {ticket_id, service, description, status, ...}
        - logs: execution logs
        - error: error message if failed
        - metadata: timing info
    """
    with ExecutorContext("create_ticket", self.request.id, sandbox=sandbox) as ctx:
        result = ctx.result
        
        if ctx.sandbox:
            return ctx.sandbox_skip(
                f"Create ticket for contact {contact_id}: {service}",
                {
                    "ticket_id": "sandbox-ticket-001",
                    "service": service,
                    "description": description[:100],
                    "status": "open",
                    "contact_id": contact_id,
                }
            )
        
        tenant, config = get_tenant_config(tenant_id)
        if not tenant:
            result.success = False
            result.error = f"Tenant not found: {tenant_id}"
            result.error_log(result.error)
            return result.to_dict()
        
        result.info(f"Creating ticket", {"service": service, "contact_id": contact_id})
        
        try:
            from crm.models import Contact
            from crm.core.tickets import create_ticket
            
            try:
                contact = Contact.objects.get(user_id=contact_id, tenant=tenant)
            except Contact.DoesNotExist:
                result.success = False
                result.error = f"Contact not found: {contact_id}"
                result.error_log(result.error)
                return result.to_dict()
            
            origin_session = None
            if origin_session_id:
                try:
                    from chatbot.models import AgentSession
                    origin_session = AgentSession.objects.get(pk=origin_session_id)
                    result.info(f"Using origin session: {origin_session_id}")
                except Exception as e:
                    result.warning(f"Origin session not found: {origin_session_id}")
            
            ticket = create_ticket(
                contact=contact,
                service=service,
                description=description,
                tenant_id=tenant_id,
                origin_session=origin_session,
            )
            
            # Emit ticket.created event for flow triggers and real-time updates
            try:
                from crm.events.ticket_events import emit_ticket_created
                from uuid import UUID
                # Use a system actor for agent-created tickets
                system_actor_id = UUID("00000000-0000-0000-0000-000000000000")
                emit_ticket_created(ticket, system_actor_id)
                result.info("Ticket creation event emitted")
            except Exception as e:
                result.warning(f"Failed to emit ticket creation event: {e}")
            
            result.success = True
            result.data = {
                "ticket_id": str(ticket.id),
                "service": service,
                "description": description,
                "status": ticket.status,
                "contact_id": contact_id,
                "message": "Ticket created successfully",
            }
            result.info(f"Ticket created: {ticket.id}")
                
        except Exception as e:
            result.success = False
            result.error = f"Failed to create ticket: {e}"
            result.error_log(result.error)
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.update_candidate_status", queue=FLOWS_Q)
def update_candidate_status_task(
    self,
    tenant_id: str,
    candidate_id: str,
    status: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update a candidate's recruitment status.
    
    Args:
        tenant_id: Tenant ID
        candidate_id: Candidate ID to update
        status: New status code (e.g., 'A' for Available, 'H' for Hired, etc.)
        notes: Optional notes about the status change
    
    Returns:
        ExecutorResult dict with:
        - success: bool
        - data: {candidate_id, new_status, previous_status, ...}
        - logs: execution logs
        - error: error message if failed
        - metadata: timing info
    """
    with ExecutorContext("update_candidate_status", self.request.id) as ctx:
        result = ctx.result
        
        tenant, config = get_tenant_config(tenant_id)
        if not tenant:
            result.success = False
            result.error = f"Tenant not found: {tenant_id}"
            result.error_log(result.error)
            return result.to_dict()
        
        result.info(f"Updating candidate status", {"candidate_id": candidate_id, "status": status})
        
        try:
            from recruiter.models import Candidate
            
            try:
                candidate = Candidate.objects.get(id=candidate_id, tenant=tenant)
            except Candidate.DoesNotExist:
                result.success = False
                result.error = f"Candidate not found: {candidate_id}"
                result.error_log(result.error)
                return result.to_dict()
            
            previous_status = candidate.recruiter_status
            candidate.recruiter_status = status
            
            if notes:
                current_notes = candidate.notes or ""
                candidate.notes = f"{current_notes}\n\n[Status Change] {notes}".strip()
            
            candidate.save()
            
            result.success = True
            result.data = {
                "candidate_id": str(candidate.id),
                "candidate_name": candidate.fullname or str(candidate.contact) if hasattr(candidate, 'contact') else "",
                "previous_status": previous_status,
                "new_status": status,
                "message": f"Candidate status updated from {previous_status} to {status}",
            }
            result.info(f"Candidate {candidate_id} status updated: {previous_status} -> {status}")
                
        except Exception as e:
            result.success = False
            result.error = f"Failed to update candidate status: {e}"
            result.error_log(result.error)
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.search_contacts", queue=FLOWS_Q)
def search_contacts_task(
    self,
    tenant_id: str,
    search_term: str,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Search contacts by name, email, or phone.
    
    Args:
        tenant_id: Tenant ID
        search_term: Search query
        limit: Maximum results to return
    
    Returns:
        ExecutorResult dict with:
        - success: bool
        - data: {contacts: [...], count: int}
        - logs: execution logs
        - error: error message if failed
        - metadata: timing info
    """
    with ExecutorContext("search_contacts", self.request.id) as ctx:
        result = ctx.result
        
        tenant, config = get_tenant_config(tenant_id)
        if not tenant:
            result.success = False
            result.error = f"Tenant not found: {tenant_id}"
            result.error_log(result.error)
            return result.to_dict()
        
        result.info(f"Searching contacts", {"term": search_term, "limit": limit})
        
        try:
            from crm.services.contact_service import ContactService
            
            contacts = ContactService.search_contacts(search_term, tenant)[:limit]
            
            contact_list = [
                {
                    "contact_id": str(c.user_id),
                    "fullname": c.fullname,
                    "phone": c.phone,
                    "email": c.email,
                }
                for c in contacts
            ]
            
            result.success = True
            result.data = {
                "contacts": contact_list,
                "count": len(contact_list),
                "search_term": search_term,
            }
            result.info(f"Found {len(contact_list)} contacts")
                
        except Exception as e:
            result.success = False
            result.error = f"Failed to search contacts: {e}"
            result.error_log(result.error)
    
    return ctx.result.to_dict()


def contact_create_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for contact creation."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "fullname": config.get("fullname") or payload.get("fullname", ""),
        "phone": config.get("phone") or payload.get("phone", ""),
        "email": config.get("email") or payload.get("email"),
        "whatsapp_name": config.get("whatsapp_name") or payload.get("whatsapp_name"),
        "source": config.get("source", "flow"),
        "contact_type_id": config.get("contact_type_id"),
        "contact_type_name": config.get("contact_type_name"),
        "custom_fields": config.get("custom_fields"),
    }
    
    if config.get("async", False):
        task = create_contact_task.apply_async(kwargs=task_kwargs)  # type: ignore[attr-defined]
        return create_result(
            success=True,
            data={"task_id": task.id, "status": "queued"},
            logs=[log_entry("INFO", f"Create contact task queued: {task.id}")],
        )
    else:
        return create_contact_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]


def contact_upsert_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for contact upsert."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "fullname": config.get("fullname") or payload.get("fullname", ""),
        "phone": config.get("phone") or payload.get("phone", ""),
        "contact_type_id": config.get("contact_type_id"),
    }
    
    if config.get("async", False):
        task = upsert_contact_task.apply_async(kwargs=task_kwargs)  # type: ignore[attr-defined]
        return create_result(
            success=True,
            data={"task_id": task.id, "status": "queued"},
            logs=[log_entry("INFO", f"Upsert contact task queued: {task.id}")],
        )
    else:
        return upsert_contact_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]


def ticket_create_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for ticket creation."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "contact_id": config.get("contact_id") or payload.get("contact_id", ""),
        "service": config.get("service") or payload.get("service", "general"),
        "description": config.get("description") or payload.get("description", ""),
        "origin_session_id": config.get("origin_session_id") or ctx.get("session_id"),
    }
    
    if config.get("async", False):
        task = create_ticket_task.apply_async(kwargs=task_kwargs)  # type: ignore[attr-defined]
        return create_result(
            success=True,
            data={"task_id": task.id, "status": "queued"},
            logs=[log_entry("INFO", f"Create ticket task queued: {task.id}")],
        )
    else:
        return create_ticket_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]


def candidate_status_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for candidate status update."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "candidate_id": config.get("candidate_id") or payload.get("candidate_id", ""),
        "status": config.get("status") or payload.get("status", ""),
        "notes": config.get("notes") or payload.get("notes"),
    }
    
    if config.get("async", False):
        task = update_candidate_status_task.apply_async(kwargs=task_kwargs)  # type: ignore[attr-defined]
        return create_result(
            success=True,
            data={"task_id": task.id, "status": "queued"},
            logs=[log_entry("INFO", f"Update candidate status task queued: {task.id}")],
        )
    else:
        return update_candidate_status_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]


def contact_search_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for contact search."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "search_term": config.get("search_term") or payload.get("search_term", ""),
        "limit": config.get("limit", 10),
    }
    
    if config.get("async", False):
        task = search_contacts_task.apply_async(kwargs=task_kwargs)  # type: ignore[attr-defined]
        return create_result(
            success=True,
            data={"task_id": task.id, "status": "queued"},
            logs=[log_entry("INFO", f"Search contacts task queued: {task.id}")],
        )
    else:
        return search_contacts_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]
