
from typing import Optional, List
from django.db import transaction

from crm.models import Ticket, Contact
from central_hub.context_utils import current_tenant


class TicketService:
    """Business logic for Ticket operations"""
    
    @staticmethod
    def create_ticket(tenant, contact: Contact, description: str, 
                     service: str = "default", ticket_type: str = "I") -> tuple[Optional[Ticket], str]:
        """
        Create a new ticket
        Returns (ticket, message)
        """
        try:
            with transaction.atomic():
                ticket = Ticket.objects.create(
                    tenant=tenant,
                    creator=contact,
                    description=description,
                    service=service,
                    type=ticket_type,
                    status="O"  # Open
                )
                
                return ticket, f"Ticket created successfully."
                
        except Exception as e:
            return None, f"Error creating ticket: {str(e)}"
    
    @staticmethod
    def get_ticket_by_id(ticket_id: str, tenant) -> Optional[Ticket]:
        """Get ticket by ID for the tenant"""
        try:
            return Ticket.objects.get(id=ticket_id, tenant=tenant)
        except Ticket.DoesNotExist:
            return None
    
    @staticmethod
    def list_open_tickets(tenant) -> List[Ticket]:
        """List all open tickets for tenant"""
        return Ticket.objects.filter(tenant=tenant).exclude(status='c').order_by('-created')
    
    OPEN_STATUSES = ["O", "A", "I", "W", "P"]
    CLOSED_STATUSES = ["C"]

    @staticmethod
    def get_ticket_counts(tenant, queryset=None) -> dict:
        """
        Get ticket counts by status and type.
        If queryset is provided, counts are based on filtered queryset.
        Otherwise, counts are for all tickets of the tenant.
        
        Status codes: O=open, A=assigned, I=in progress, W=waiting, C=closed, P=planned
        Type codes: I=incident, C=change, P=planned
        """
        if queryset is None:
            queryset = Ticket.objects.filter(tenant=tenant)
        
        return {
            'open': queryset.filter(status__in=TicketService.OPEN_STATUSES).count(),
            'incidents': queryset.filter(type="I").count(),
            'changes': queryset.filter(type="C").count(),
            'planned': queryset.filter(type="P").count(),
            'waiting': queryset.filter(status="W").count(),
            'in_progress': queryset.filter(status="I").count(),
            'closed': queryset.filter(status__in=TicketService.CLOSED_STATUSES).count(),
            'total': queryset.count(),
        }
    
    @staticmethod
    def update_ticket_status(ticket: Ticket, new_status: str) -> tuple[bool, str]:
        """
        Update ticket status
        Returns (success, message)
        """
        try:
            ticket.status = new_status
            ticket.save()
            return True, f"Ticket status updated to {new_status}."
        except Exception as e:
            return False, f"Error updating ticket: {str(e)}"
