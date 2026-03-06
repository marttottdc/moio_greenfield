
from typing import Optional, Dict, Any
from django.db import transaction
from django.contrib import messages
from django.http import HttpRequest

from crm.models import Contact, ContactType
from portal.context_utils import current_tenant
import logging
logger = logging.getLogger(__name__)

class ContactService:
    """Business logic for Contact operations"""
    
    @staticmethod
    def create_contact(tenant, fullname: str, email: str = '', phone: str = '',
                      whatsapp_name: str = '', source: str = '', 
                      ctype_name: str = None, ctype_pk: str = None) -> tuple[Optional[Contact], str]:
        """
        Create a new contact with validation
        Returns (contact, message)
        """
        # Validate required fields
        if not fullname or not phone:
            return None, "Full name and phone are required."
        
        try:
            with transaction.atomic():
                # Get or create contact type if specified
                ctype = None
                if ctype_name:
                    ctype, created = ContactType.objects.get_or_create(
                        name=ctype_name,
                        tenant=tenant
                    )
                elif ctype_pk:
                    ctype = ContactType.objects.get(pk=ctype_pk)

                # Create the contact
                contact = Contact.create_or_update(
                    tenant=tenant,
                    fullname=fullname,
                    email=email,
                    phone=phone,
                    whatsapp_name=whatsapp_name,
                    source=source,
                    ctype=ctype
                )
                
                if contact:
                    return contact, f"Contact '{fullname}' created successfully."
                else:
                    return None, "Failed to create contact."
                    
        except ValueError as e:
            return None, str(e)
        except Exception as e:
            return None, f"Error creating contact: {str(e)}"
    
    @staticmethod
    def search_contacts(search_term: str, tenant):
        """Search contacts by term"""
        return Contact.objects.search(search_term, tenant=tenant)
    
    @staticmethod
    def get_contact_by_id(contact_id: str, tenant):
        """Get contact by ID for the tenant"""
        try:
            return Contact.objects.get(user_id=contact_id, tenant=tenant)
        except Contact.DoesNotExist:
            return None
    
    @staticmethod
    def list_contacts(tenant, limit: Optional[int] = None):
        """List all contacts for tenant"""
        queryset = Contact.objects.filter(tenant=tenant)
        if limit:
            queryset = queryset[:limit]
        return queryset

    @staticmethod
    def contact_upsert(tenant, fullname, phone, ctype_pk):

        try:
            ctype = ContactType.objects.get(id=ctype_pk)

        except ContactType.DoesNotExist:
            raise ValueError(f"Contact type '{ctype_pk}' does not exist")

        try:
            contact = Contact.objects.get(phone=phone, tenant=tenant)
            logger.info(f"Contact found {contact}")

        except Contact.DoesNotExist:

            contact = Contact.objects.create(tenant=tenant, phone=phone, fullname=fullname, ctype=ctype)
            logger.info(f"Contact created {contact}")

        return contact

    @staticmethod
    def promote_contact_to_user(
        contact_id: str,
        tenant,
        password: str,
        username: str = None,
        send_welcome_email: bool = False
    ) -> tuple[Optional[Any], str]:
        """
        Promote a Contact to a User account.
        
        Creates a MoioUser from an existing Contact and links them.
        The Contact's ctype is updated to 'User' and linked_user is set.
        
        Args:
            contact_id: The Contact's user_id (primary key)
            tenant: The tenant for the operation
            password: Password for the new user account
            username: Optional username (defaults to email)
            send_welcome_email: Whether to send welcome email
            
        Returns:
            (user, message) tuple - user is None on failure
        """
        from portal.models import MoioUser
        
        try:
            contact = Contact.objects.get(user_id=contact_id, tenant=tenant)
        except Contact.DoesNotExist:
            return None, "Contact not found"
        
        if contact.linked_user:
            return None, "Contact is already linked to a user account"
        
        if not contact.email:
            return None, "Contact must have an email address to be promoted to user"
        
        existing_user = MoioUser.objects.filter(email__iexact=contact.email).first()
        if existing_user:
            return None, f"A user with email {contact.email} already exists"
        
        final_username = username or contact.email
        existing_username = MoioUser.objects.filter(username__iexact=final_username).first()
        if existing_username:
            return None, f"Username {final_username} is already taken"
        
        try:
            with transaction.atomic():
                user = MoioUser.objects.create_user(
                    email=contact.email,
                    username=final_username,
                    password=password,
                    first_name=contact.first_name or contact.fullname.split()[0] if contact.fullname else "",
                    last_name=contact.last_name or " ".join(contact.fullname.split()[1:]) if contact.fullname else "",
                    tenant=tenant,
                    phone=contact.phone or "",
                )
                
                user_ctype, _ = ContactType.objects.get_or_create(
                    name="User",
                    tenant=tenant,
                )
                
                contact.linked_user = user
                contact.ctype = user_ctype
                contact.save(update_fields=["linked_user", "ctype"])
                
                logger.info(f"Contact {contact_id} promoted to user {user.id}")
                return user, "Contact successfully promoted to user"
                
        except Exception as e:
            logger.error(f"Error promoting contact {contact_id}: {e}")
            return None, f"Error creating user account: {str(e)}"



