"""
Messaging Executors - WhatsApp & Email Functions

Synchronous executor functions for sending messages, designed to run
within a flow execution task. These are called directly from the flow
runtime (which is already a Celery task).

Both functions return structured ExecutorResult for downstream chaining.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from .base import (
    ExecutorResult,
    ExecutorContext,
    create_result,
    create_error_result,
    get_tenant_config,
    log_entry,
    _now_iso,
)

logger = logging.getLogger(__name__)


def send_whatsapp_template(
    tenant_id: str,
    template_id: str,
    values: Union[Dict[str, Any], List[Dict[str, Any]]] = None,
    parameters: Union[Dict[str, Any], List[Dict[str, Any]]] = None,
    files: Optional[Dict[str, Any]] = None,
    save_contact: bool = False,
    contact_type_id: Optional[str] = None,
    notify_agent: bool = False,
    flow_context: Optional[str] = None,
    sandbox: bool = False,
    flow_execution_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send WhatsApp template message(s) with optional contact upsert and agent notification.
    
    Supports batch sending - pass a list of dicts to `values` for multiple recipients.
    
    Args:
        tenant_id: Tenant ID for configuration lookup
        template_id: WhatsApp template name/ID to use
        values: Single dict or list of dicts with template variables.
                Each dict must contain 'whatsapp_number' and template params.
        parameters: Alias for `values` (for backwards compatibility)
        files: Optional file attachments for document/image templates
        save_contact: If True, upsert contact before sending
        contact_type_id: Contact type ID for contact upsert
        notify_agent: If True, register message with agent for response handling
        flow_context: Context for agent notification
        sandbox: If True, skip actual API call and return simulated result
        flow_execution_id: Optional FlowExecution UUID for tracing message lifecycle
    
    Returns:
        ExecutorResult dict with:
        - success: bool
        - data: {sent_count, failed_count, results: [...], message_logs: [...]}
        - logs: execution logs
        - error: error message if failed
        - metadata: timing info
    """
    # Handle backwards compatibility: parameters is alias for values
    if parameters is not None and values is None:
        values = parameters
    
    if values is None:
        values = {}
    
    with ExecutorContext("send_whatsapp_template", None, sandbox=sandbox) as ctx:
        result = ctx.result
        
        batch = values if isinstance(values, list) else [values]
        batch_phones = [v.get("whatsapp_number", "unknown") for v in batch[:3]]
        
        if ctx.sandbox:
            return ctx.sandbox_skip(
                f"Send WhatsApp template '{template_id}' to {len(batch)} recipient(s): {batch_phones}",
                {
                    "template_id": template_id,
                    "sent_count": len(batch),
                    "failed_count": 0,
                    "results": [
                        {"index": i, "success": True, "message_id": f"sandbox-msg-{i}", "phone": v.get("whatsapp_number")}
                        for i, v in enumerate(batch)
                    ],
                }
            )
        
        tenant, config = get_tenant_config(tenant_id)
        if not tenant or not config:
            result.success = False
            result.error = f"Tenant or config not found for {tenant_id}"
            result.error_log(result.error)
            return result.to_dict()
        
        if not config.whatsapp_integration_enabled:
            result.success = False
            result.error = "WhatsApp integration not enabled for this tenant"
            result.error_log(result.error)
            return result.to_dict()
        
        try:
            from chatbot.lib.whatsapp_client_api import WhatsappBusinessClient
            from chatbot.lib.whatsapp_client_api import (
                template_requirements,
                build_whatsapp_components,
                compose_template_based_message,
            )
        except ImportError as e:
            result.success = False
            result.error = f"WhatsApp client library not available: {e}"
            result.error_log(result.error)
            return result.to_dict()
        
        wa = WhatsappBusinessClient(config)
        result.info("WhatsApp client initialized")
        
        try:
            template = wa.template_details(template_id)
            requirements = template_requirements(template)
            namespace = wa.retrieve_template_namespace()
            result.info(f"Template '{template_id}' loaded", {"requirements": str(requirements)})
        except Exception as e:
            result.success = False
            result.error = f"Failed to load template '{template_id}': {e}"
            result.error_log(result.error)
            return result.to_dict()
        
        batch = values if isinstance(values, list) else [values]
        files = files or {}
        
        sent_count = 0
        failed_count = 0
        results: List[Dict[str, Any]] = []

        for idx, template_vars in enumerate(batch):
            phone = template_vars.get("whatsapp_number")
            if not phone:
                failed_count += 1
                results.append({
                    "index": idx,
                    "success": False,
                    "error": "Missing whatsapp_number in values",
                })
                result.warning(f"Batch item {idx}: missing whatsapp_number")
                continue

            try:
                # ----------------------------
                # Attachment resolution
                # ----------------------------
                if template_vars.get("document_link") == "attachment":
                    if files.get("attachment", {}).get("url"):
                        template_vars["document_link"] = files["attachment"]["url"]

                if template_vars.get("image_link") == "attachment":
                    if files.get("attachment", {}).get("url"):
                        template_vars["image_link"] = files["attachment"]["url"]

                # ----------------------------
                # Optional contact upsert
                # ----------------------------
                contact = None
                if save_contact:
                    try:
                        from crm.services.contact_service import ContactService

                        fullname = (
                                template_vars.get("contact_name")
                                or template_vars.get("fullname")
                                or phone
                        )
                        contact = ContactService.contact_upsert(
                            tenant=tenant,
                            fullname=fullname,
                            phone=phone,
                            ctype_pk=contact_type_id,
                        )
                        result.info(
                            f"Contact upserted: {contact.id}",
                            {"phone": phone},
                        )
                    except Exception as e:
                        result.warning(f"Contact upsert failed for {phone}: {e}")

                # ----------------------------
                # ✅ WhatsApp-correct rendering
                # ----------------------------
                components = build_whatsapp_components(
                    template=template,
                    values=template_vars,
                )

                msg = compose_template_based_message(
                    template=template,
                    phone=phone,
                    namespace=namespace,
                    components=components,
                )

                send_result = wa.send_message(msg, "template")
                
                api_response = send_result.get("response") if isinstance(send_result, dict) else send_result
                is_success = send_result.get("success", False) if isinstance(send_result, dict) else bool(send_result)
                api_error = send_result.get("error", "") if isinstance(send_result, dict) else ""

                if is_success:
                    sent_count += 1
                    message_id = (
                        api_response.get("messages", [{}])[0].get("id")
                        if isinstance(api_response, dict)
                        else None
                    )
                    
                    wa_log_id = None
                    try:
                        from chatbot.models.wa_message_log import WaMessageLog
                        from django.utils.timezone import now as django_now
                        wa_log = WaMessageLog.objects.create(
                            tenant=tenant,
                            msg_id=message_id,
                            type="template",
                            status="sent" if message_id else "sent_pending_id",
                            user_number=phone,
                            recipient_id=phone,
                            body=f"Template: {template_id}",
                            msg_content={"template_id": template_id, "values": template_vars},
                            flow_execution_id=flow_execution_id,
                            api_response=api_response,
                            timestamp=django_now(),
                        )
                        wa_log_id = wa_log.pk
                        result.info(f"WaMessageLog created: {wa_log_id}")
                    except Exception as log_err:
                        result.warning(f"Failed to create WaMessageLog: {log_err}")

                    results.append({
                        "index": idx,
                        "success": True,
                        "phone": phone,
                        "message_id": message_id,
                        "contact_id": str(contact.id) if contact else None,
                        "api_response": api_response,
                        "wa_log_id": wa_log_id,
                    })
                    result.info(
                        f"Message sent to {phone}",
                        {"message_id": message_id},
                    )

                    # ----------------------------
                    # Optional agent notification
                    # ----------------------------
                    if notify_agent and contact:
                        try:
                            from chatbot.core.moio_agent import AgentEngine

                            agent = AgentEngine(
                                config,
                                contact,
                                started_by=f"flow: {flow_context or 'WhatsApp Template'}",
                            )

                            notification = f"""Outgoing WhatsApp template message sent.
        Template: {template_id}
        Recipient: {phone}
        Context: {flow_context or 'Automated flow'}
        Parameters: {template_vars}
        """
                            agent.register_outgoing_campaign_message(notification)
                            result.info(f"Agent notified for {phone}")
                        except Exception as e:
                            result.warning(
                                f"Agent notification failed for {phone}: {e}"
                            )

                else:
                    failed_count += 1
                    error_detail = api_error or "Send failed (unknown reason)"
                    
                    wa_log_id = None
                    try:
                        from chatbot.models.wa_message_log import WaMessageLog
                        from django.utils.timezone import now as django_now
                        wa_log = WaMessageLog.objects.create(
                            tenant=tenant,
                            type="template",
                            status="failed",
                            user_number=phone,
                            recipient_id=phone,
                            body=f"Template: {template_id}",
                            msg_content={"template_id": template_id, "values": template_vars, "error": error_detail},
                            flow_execution_id=flow_execution_id,
                            api_response=api_response,
                            timestamp=django_now(),
                        )
                        wa_log_id = wa_log.pk
                    except Exception as log_err:
                        result.warning(f"Failed to create WaMessageLog for failure: {log_err}")
                    
                    results.append({
                        "index": idx,
                        "success": False,
                        "phone": phone,
                        "error": error_detail,
                        "api_response": api_response,
                        "wa_log_id": wa_log_id,
                    })
                    result.warning(f"Message send failed for {phone}: {error_detail}")

            except Exception as e:
                failed_count += 1
                
                wa_log_id = None
                try:
                    from chatbot.models import WaMessageLog
                    from django.utils.timezone import now as django_now
                    wa_log = WaMessageLog.objects.create(
                        tenant=tenant,
                        type="template",
                        status="error",
                        user_number=phone,
                        recipient_id=phone,
                        body=f"Template: {template_id}",
                        msg_content={"template_id": template_id, "values": template_vars, "error": str(e)},
                        flow_execution_id=flow_execution_id,
                        timestamp=django_now(),
                    )
                    wa_log_id = wa_log.pk
                except Exception as log_err:
                    result.warning(f"Failed to create WaMessageLog for error: {log_err}")
                
                results.append({
                    "index": idx,
                    "success": False,
                    "phone": phone,
                    "error": str(e),
                    "wa_log_id": wa_log_id,
                })
                result.error_log(f"Error sending to {phone}: {e}")
        
        result.data = {
            "sent_count": sent_count,
            "failed_count": failed_count,
            "total": len(batch),
            "results": results,
            "template_id": template_id,
        }
        
        if failed_count > 0 and sent_count == 0:
            result.success = False
            result.error = f"All {failed_count} messages failed to send"
        elif failed_count > 0:
            result.success = True
            result.warning(f"{failed_count} of {len(batch)} messages failed")
        else:
            result.success = True
        
        result.info(f"Batch complete: {sent_count} sent, {failed_count} failed")
        
    return ctx.result.to_dict()


def send_email_template(
    tenant_id: str,
    template_id: str,
    values: Dict[str, Any],
    files: Optional[Dict[str, Any]] = None,
    sandbox: bool = False,
) -> Dict[str, Any]:
    """
    Send templated email using tenant SMTP configuration.
    
    Args:
        tenant_id: Tenant ID for configuration lookup
        template_id: Template name to render (looked up in email/ templates)
        values: Template variables including 'email' (recipient) and 'subject'
        files: Optional file attachments {name: {url or content_base64, filename, content_type}}
        sandbox: If True, skip actual sending and return simulated result
    
    Returns:
        ExecutorResult dict with:
        - success: bool
        - data: {recipient, subject, template_id}
        - logs: execution logs
        - error: error message if failed
        - metadata: timing info
    """
    with ExecutorContext("send_email_template", None, sandbox=sandbox) as ctx:
        result = ctx.result
        
        recipient = values.get("email")
        subject = values.get("subject", "No Subject")
        
        if ctx.sandbox:
            return ctx.sandbox_skip(
                f"Send email to {recipient}: {subject}",
                {
                    "recipient": recipient,
                    "subject": subject,
                    "template_id": template_id,
                    "message_id": "sandbox-email-001",
                }
            )
        
        # ────────────── 1. payload basics ──────────────
        if not recipient:
            result.success = False
            result.error = "No email address in values"
            result.error_log(result.error)
            return result.to_dict()
        
        # ────────────── 2. SMTP guard ──────────────
        tenant, config = get_tenant_config(tenant_id)
        if not tenant or not config:
            result.success = False
            result.error = f"Tenant or config not found for {tenant_id}"
            result.error_log(result.error)
            return result.to_dict()
        
        if not config.smtp_integration_enabled:
            result.success = False
            result.error = "SMTP integration not enabled for this tenant"
            result.error_log(result.error)
            return result.to_dict()
        
        result.info(f"Preparing email to {recipient}", {"subject": subject, "template": template_id})
        
        try:
            from django.core.mail import EmailMessage, get_connection
            from django.template.loader import select_template
            from moio_platform.lib.email import attach_files
        except ImportError as e:
            result.success = False
            result.error = f"Email library not available: {e}"
            result.error_log(result.error)
            return result.to_dict()
        
        # ────────────── 3. subject & body ──────────────
        template_names = [
            f"central_hub/templates/email/{template_id}.html",
            f"templates/email/{template_id}.html",
            f"email/{template_id}.html",
        ]
        
        try:
            html_body = select_template(template_names).render({
                "data": values
            })
            result.info(f"Template '{template_id}' rendered successfully")
        except Exception as exc:
            result.success = False
            result.error = f"Template render failed: {exc}"
            result.error_log(result.error)
            return result.to_dict()
        
        # ────────────── 4. build e-mail ──────────────
        try:
            connection = get_connection(
                host=config.smtp_host,
                port=config.smtp_port,
                username=config.smtp_user,
                password=config.smtp_password,
                use_tls=config.smtp_use_tls,
                timeout=30,
            )
            result.info("SMTP connection configured", {
                "host": config.smtp_host,
                "port": config.smtp_port,
            })
        except Exception as exc:
            result.success = False
            result.error = f"SMTP connection failed: {exc}"
            result.error_log(result.error)
            return result.to_dict()
        
        try:
            email_msg = EmailMessage(
                subject=subject,
                body=html_body,
                from_email=config.smtp_user,
                to=[recipient],
                connection=connection,
            )
            email_msg.content_subtype = "html"
            
            # ────────────── 5. attachments (URL or base64) ──────────────
            if files:
                attach_files(email_msg, files)
                result.info(f"Attached {len(files)} file(s)")
            
            # ────────────── 6. send ──────────────
            send_result = email_msg.send()
            
            if send_result == 1:
                result.success = True
                result.data = {
                    "recipient": recipient,
                    "subject": subject,
                    "template_id": template_id,
                    "message": "Email sent successfully",
                }
                result.info(f"Email sent successfully to {recipient}")
            else:
                result.success = False
                result.error = f"Email send returned non-1 status: {send_result}"
                result.error_log(result.error)
                
        except Exception as exc:
            result.success = False
            result.error = f"SMTP send error: {exc}"
            result.error_log(result.error)
    
    return ctx.result.to_dict()
