from typing import Optional
from crm.models import Ticket, TicketComment, Contact


def create_ticket(contact, service, description, tenant_id, origin_session=None):
    """
    Create a new ticket with optional origin tracking.
    
    Args:
        contact: The contact creating/associated with the ticket
        service: Service category for the ticket
        description: Ticket description
        tenant_id: Tenant ID
        origin_session: Optional AgentSession - if provided, automatically sets
                       origin_type='chatbot', origin_session FK, and origin_ref
    
    Returns:
        The created Ticket instance
    """
    ticket_data = {
        'service': service,
        'description': description,
        'creator': contact,
        'tenant_id': tenant_id,
        'status': 'O',
    }
    
    if origin_session:
        ticket_data['origin_type'] = 'chatbot'
        ticket_data['origin_session'] = origin_session
        ticket_data['origin_ref'] = str(origin_session.pk)
    
    ticket = Ticket.objects.create(**ticket_data)
    ticket.save()

    return ticket


