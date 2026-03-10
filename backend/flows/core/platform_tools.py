"""
Platform Tools for Flows

Reusable tools that can be:
1. Attached to AI agents as function tools
2. Executed as standalone flow nodes (outputs)

These tools integrate with platform features (CRM, Chatbot, Recruiter, etc.)
"""

from typing import Dict, Any, Optional
import logging

from flows.core.executors import send_whatsapp_template

logger = logging.getLogger(__name__)


# ============================================================================
# CRM Tools
# ============================================================================

def create_crm_contact(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    company: Optional[str] = None,
    notes: Optional[str] = None,
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new contact in the CRM system
    
    Args:
        name: Contact's full name
        email: Contact's email address
        phone: Contact's phone number
        company: Company name
        notes: Additional notes about the contact
        tenant_id: Tenant ID (auto-populated from flow context)
        
    Returns:
        Dict with contact details including ID
    """
    from crm.services.contact_service import create_contact
    from central_hub.models import Tenant
    
    try:
        tenant = Tenant.objects.get(id=tenant_id) if tenant_id else None
        
        contact_data = {
            "name": name,
            "email": email or "",
            "phone": phone or "",
            "company": company or "",
            "notes": notes or "",
        }
        
        contact = create_contact(contact_data, tenant=tenant)
        
        return {
            "success": True,
            "contact_id": str(contact.id),
            "name": contact.name,
            "email": contact.email,
            "message": f"Contact '{name}' created successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to create contact: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to create contact: {str(e)}"
        }


def create_crm_ticket(
    title: str,
    description: str,
    contact_id: Optional[str] = None,
    priority: str = "medium",
    category: str = "general",
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a support ticket in the CRM system
    
    Args:
        title: Ticket title/subject
        description: Detailed description of the issue
        contact_id: ID of the related contact (optional)
        priority: Ticket priority (low, medium, high, urgent)
        category: Ticket category
        tenant_id: Tenant ID (auto-populated from flow context)
        
    Returns:
        Dict with ticket details including ID
    """
    from crm.core.tickets import create_ticket
    from central_hub.models import Tenant
    from crm.models import Contact
    
    try:
        tenant = Tenant.objects.get(id=tenant_id) if tenant_id else None
        contact = None
        
        if contact_id:
            try:
                contact = Contact.objects.get(id=contact_id, tenant=tenant)
            except Contact.DoesNotExist:
                logger.warning(f"Contact {contact_id} not found for ticket creation")
        
        ticket = create_ticket(
            title=title,
            description=description,
            contact=contact,
            priority=priority,
            category=category,
            tenant=tenant
        )
        
        return {
            "success": True,
            "ticket_id": str(ticket.id) if hasattr(ticket, 'id') else None,
            "title": title,
            "priority": priority,
            "message": f"Ticket '{title}' created successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to create ticket: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to create ticket: {str(e)}"
        }


# ============================================================================
# Chatbot / WhatsApp Tools
# ============================================================================

def send_whatsapp_message(
    phone: str,
    message: str,
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send a WhatsApp message
    
    Args:
        phone: Recipient's phone number (with country code)
        message: Message text to send
        tenant_id: Tenant ID (auto-populated from flow context)
        
    Returns:
        Dict with send status and message ID
    """
    from chatbot.lib.whatsapp_client_api import send_text_message
    from central_hub.models import Tenant
    
    try:
        tenant = Tenant.objects.get(id=tenant_id) if tenant_id else None
        config = tenant.configuration.first() if tenant else None
        
        if not config or not config.whatsapp_integration_enabled:
            return {
                "success": False,
                "error": "WhatsApp integration not enabled for this tenant",
                "message": "WhatsApp not configured"
            }
        
        result = send_text_message(phone, message, tenant=tenant)
        
        return {
            "success": True,
            "message_id": result.get('message_id'),
            "phone": phone,
            "message": "WhatsApp message sent successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to send WhatsApp message: {str(e)}"
        }


# ============================================================================
# Recruiter Tools
# ============================================================================

def update_candidate_status(
    candidate_id: str,
    status: str,
    notes: Optional[str] = None,
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update a candidate's status in the recruiter system
    
    Args:
        candidate_id: ID of the candidate to update
        status: New status (e.g., 'screening', 'interviewing', 'hired', 'rejected')
        notes: Optional notes about the status change
        tenant_id: Tenant ID (auto-populated from flow context)
        
    Returns:
        Dict with update status
    """
    from recruiter.models import Candidate
    from central_hub.models import Tenant
    
    try:
        tenant = Tenant.objects.get(id=tenant_id) if tenant_id else None
        
        candidate = Candidate.objects.get(id=candidate_id, tenant=tenant)
        candidate.recruiter_status = status
        
        if notes:
            # Append notes to existing notes
            current_notes = candidate.notes or ""
            candidate.notes = f"{current_notes}\n\n[Status Change] {notes}".strip()
        
        candidate.save()
        
        return {
            "success": True,
            "candidate_id": str(candidate.id),
            "candidate_name": candidate.name,
            "new_status": status,
            "message": f"Candidate status updated to '{status}'"
        }
        
    except Candidate.DoesNotExist:
        return {
            "success": False,
            "error": "Candidate not found",
            "message": f"Candidate {candidate_id} not found"
        }
    except Exception as e:
        logger.error(f"Failed to update candidate status: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to update candidate status: {str(e)}"
        }


# ============================================================================
# Generic Tools
# ============================================================================

def send_email(
    to: str | list[str],
    subject: str,
    body: str,
    from_email: Optional[str] = None,
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send an email
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text or HTML)
        from_email: Sender email (optional, uses tenant default)
        tenant_id: Tenant ID (auto-populated from flow context)
        
    Returns:
        Dict with send status
    """
    from django.core.mail import EmailMultiAlternatives
    from django.conf import settings
    
    try:
        from_addr = from_email or settings.DEFAULT_FROM_EMAIL

        recipients = [to] if isinstance(to, str) else list(to or [])
        recipients = [r for r in recipients if r]

        # If body looks like HTML, send as HTML alternative.
        body_str = body or ""
        looks_html = "<" in body_str and ">" in body_str and "</" in body_str

        msg = EmailMultiAlternatives(
            subject=subject,
            body=body_str if not looks_html else "",
            from_email=from_addr,
            to=recipients,
        )
        if looks_html:
            msg.attach_alternative(body_str, "text/html")

        msg.send(fail_silently=False)
        
        return {
            "success": True,
            "to": to,
            "subject": subject,
            "message": f"Email sent to {to}"
        }
        
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to send email: {str(e)}"
        }


def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Make an HTTP request to an external API
    
    Args:
        url: The URL to request
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        headers: Optional HTTP headers
        body: Optional request body (for POST/PUT)
        
    Returns:
        Dict with response status and data
    """
    import requests
    
    try:
        headers = headers or {}
        
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, json=body, headers=headers, timeout=30)
        elif method.upper() == "PUT":
            response = requests.put(url, json=body, headers=headers, timeout=30)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers, timeout=30)
        else:
            return {
                "success": False,
                "error": f"Unsupported HTTP method: {method}"
            }
        
        try:
            response_data = response.json()
        except:
            response_data = response.text
        
        return {
            "success": response.ok,
            "status_code": response.status_code,
            "data": response_data,
            "message": f"HTTP {method} request completed with status {response.status_code}"
        }
        
    except Exception as e:
        logger.error(f"HTTP request failed: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": f"HTTP request failed: {str(e)}"
        }


# ============================================================================
# Tool Registry
# ============================================================================

PLATFORM_TOOLS = {
    # CRM
    "create_contact": create_crm_contact,
    "create_ticket": create_crm_ticket,
    
    # WhatsApp / Chatbot
    "send_whatsapp": send_whatsapp_message,
    "send_whatsapp_template": send_whatsapp_template,
    
    # Recruiter
    "update_candidate_status": update_candidate_status,
    
    # Generic
    "send_email": send_email,
    "http_request": http_request,
}


def get_platform_tool(name: str):
    """Get a platform tool by name"""
    if name not in PLATFORM_TOOLS:
        raise ValueError(f"Unknown platform tool: {name}")
    return PLATFORM_TOOLS[name]


def list_platform_tools():
    """List all available platform tools"""
    return list(PLATFORM_TOOLS.keys())
