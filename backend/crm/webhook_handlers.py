import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from pgvector.django import L2Distance

from chatbot.lib.whatsapp_client_api import compose_template_based_message, replace_template_placeholders, \
    WhatsappBusinessClient, template_requirements

from central_hub.webhooks.registry import webhook_handler
from central_hub.tenant_config import get_tenant_config
from crm.models import KnowledgeItem, Face, WebhookPayload
from crm.tasks import process_shopify_webhook
from moio_platform.lib.openai_gpt_api import MoioOpenai
import json
import logging

from moio_platform.lib.email import extract_form_from_payload, attach_files, json_to_email_html


from django.core.mail import EmailMessage, get_connection
from django.template.loader import render_to_string, select_template
from transformers import AutoTokenizer

logger = logging.getLogger(__name__)


try:
    _TOKENIZER = AutoTokenizer.from_pretrained("gpt2")  # tiny + license-friendly
except Exception as exc:  # pragma: no cover - exercised in offline test environments
    logger.warning("Falling back to simple tokenizer: %s", exc)

    class _SimpleTokenizer:
        """Minimal whitespace tokenizer used when the HF model is unavailable."""

        def encode(self, text: str):
            return text.split()

        def decode(self, tokens):
            if isinstance(tokens, list):
                return " ".join(tokens)
            return str(tokens)

    _TOKENIZER = _SimpleTokenizer()


def n_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text))


def chunk_text(
    text: str,
    max_tokens: int = 600,
    overlap: int = 100,
):
    """Yield text chunks with sliding-window overlap."""
    sentences = text.split("\n")
    buff, buff_tokens = [], 0

    for sent in sentences:
        stoks = n_tokens(sent)
        # flush if adding this sentence would overflow the window
        if buff_tokens + stoks > max_tokens and buff:
            yield " ".join(buff).strip()
            # start new buffer with trailing overlap
            overlap_text = _TOKENIZER.decode(
                _TOKENIZER.encode(" ".join(buff))[-overlap:]
            )
            buff, buff_tokens = [overlap_text], n_tokens(overlap_text)
        buff.append(sent)
        buff_tokens += stoks

    if buff:
        yield " ".join(buff).strip()

# --------- main handler ------------------------------------------------------


@webhook_handler()
def kb_from_article(payload, headers, content_type, cfg):
    """
    Ingest a JSON article into multiple KnowledgeItem rows (one per chunk).
    Payload MUST contain: title, url, content.
    """

    tenant_cfg = get_tenant_config(cfg.tenant)

    ai = MoioOpenai(
        api_key=tenant_cfg.openai_api_key,
        default_model=tenant_cfg.openai_default_model,
    )

    title     = payload["title"].strip()
    url       = payload["url"].strip()
    body      = payload["content"]
    chunks    = list(chunk_text(body))

    system_instructions = (
        "You are a knowledge-base extractor.\n"
        "Return JSON:\n"
        "{\n"
        '  "title":   "<10-word headline>",\n'
        '  "description": "<plain-text summary, max 800 chars>",\n'
        "}\n"
        "Remove ALL HTML/markup. No extra keys."
    )

    created, updated = 0, 0
    with transaction.atomic():
        for idx, chunk in enumerate(chunks, start=1):
            # ------------- call LLM ------------------------------------------------
            llm_resp = ai.json_response(
                data=json.dumps({"content": chunk}),
                system_instructions=system_instructions,
            )
            clean = json.loads(llm_resp)

            # ------------- enrich & save ------------------------------------------
            clean.update(
                {
                    "tenant": cfg.tenant,
                    "url": url,
                    "chunk_index": idx,
                    "chunk_count": len(chunks),
                    "slug": slugify(f"{title}-{idx}"),
                }
            )

            obj, is_created = KnowledgeItem.objects.update_or_create(
                tenant=cfg.tenant,
                slug=clean["slug"],
                defaults=clean,
            )
            created += is_created
            updated += (not is_created)

    logger.info(
        "kb_from_article: %s created · %s updated (url=%s)",
        created,
        updated,
        url,
    )
    return {
        "msg": f"ingested {len(chunks)} chunk(s)",
        "created": created,
        "updated": updated,
    }


@webhook_handler()
def default_handler(payload, headers, content_type, cfg):
    print(payload)

    new_payload = WebhookPayload.objects.create(payload=payload, tenant=cfg.tenant)
    return payload


@webhook_handler()
def email_back(payload, headers, content_type, cfg):

    # ────────────── 1. payload basics ──────────────
    media_type = content_type.split(";", 1)[0].strip().lower()
    form = extract_form_from_payload(payload, media_type)

    recipient = form.get("email")
    if not recipient:
        logger.warning("No email address in payload; aborting.")
        return

    # ────────────── 2. SMTP guard ──────────────
    config = get_tenant_config(cfg.tenant)
    if not config.smtp_integration_enabled:
        raise Exception("SMTP integration disabled")

    # ────────────── 3. subject & body ──────────────
    subject = form.get("subject", "webhook processed")

    # ---------- NEW: render HTML with a Django template ----------
    #
    #  • looks first for tenant-specific template:   emails/<tenant_slug>/payload.html
    #  • falls back to a generic template:          emails/payload.html
    #
    #  The whole form dict is passed in `data`.
    #  A prettified JSON version is passed in `data_json` (handy for <pre> blocks).

    tenant_slug = cfg.tenant.slug if hasattr(cfg.tenant, "slug") else str(cfg.tenant_id)
    template_names = [

        "central_hub/templates/email/payload.html",
        "templates/email/payload.html",
        "email/payload.html",
    ]

    try:
        html_body = select_template(template_names).render({
            "data": form,
            "data_json": json.dumps(form, indent=2, ensure_ascii=False),
        })

        # ────────────── 4. build e-mail ──────────────
        connection = get_connection(
            host=config.smtp_host,
            port=config.smtp_port,
            username=config.smtp_user,
            password=config.smtp_password,
            use_tls=config.smtp_use_tls,
            timeout=30,
        )

        email_msg = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=config.smtp_user,
            to=[recipient],
            connection=connection,
        )
        email_msg.content_subtype = "html"

        # ────────────── 5. attachments (URL or base64) ──────────────
        attach_files(email_msg, payload.get("files", {}))

        # ────────────── 6. send ──────────────
        try:
            if email_msg.send() == 1:
                logger.info("Email sent successfully")
                return {"msg": "Email sent successfully"}
            else:
                logger.error("Email send returned non-1 status")
                return {"msg": "Email send returned non-1 status"}
        except Exception as exc:
            logger.error("SMTP send error: %s", exc)
            return {"msg": "SMTP send error"}

    except Exception as exc:            # template missing or syntax error
        logger.error("Template render failed, falling back to raw HTML: %s", exc)

    # ----------------------------------------------------------------


@webhook_handler()
def email_template_sender(payload, headers, content_type, cfg):
    # ────────────── 1. payload basics ──────────────

    content = payload.get("values")
    template_id = payload.get("template_id")
    recipient = content.get("email")

    if not recipient:
        logger.warning("No email address in payload; aborting.")
        return

    # ────────────── 2. SMTP guard ──────────────
    config = get_tenant_config(cfg.tenant)
    if not config.smtp_integration_enabled:
        raise Exception("SMTP integration disabled")

    # ────────────── 3. subject & body ──────────────
    subject = content.get("subject", "No Subject")

    # ---------- NEW: render HTML with a Django template ----------
    #
    #  • looks first for tenant-specific template:   emails/<tenant_slug>/payload.html
    #  • falls back to a generic template:          emails/payload.html
    #
    #  The whole form dict is passed in `data`.
    #  A prettified JSON version is passed in `data_json` (handy for <pre> blocks).

    template_names = [
        f"central_hub/templates/email/{template_id}.html",
        f"templates/email/{template_id}.html",
        f"email/{template_id}.html",
    ]

    try:
        html_body = select_template(template_names).render({
            "data": content
        })

        # ────────────── 4. build e-mail ──────────────

        connection = get_connection(
            host=config.smtp_host,
            port=config.smtp_port,
            username=config.smtp_user,
            password=config.smtp_password,
            use_tls=config.smtp_use_tls,
            timeout=30,
        )

        email_msg = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=config.smtp_user,
            to=[recipient],
            connection=connection,
        )
        email_msg.content_subtype = "html"

        # ────────────── 5. attachments (URL or base64) ──────────────
        attach_files(email_msg, payload.get("files", {}))

        # ────────────── 6. send ──────────────
        try:
            if email_msg.send() == 1:
                logger.info("Email sent successfully")
                return {"msg": "Email sent successfully"}
            else:
                logger.error("Email send returned non-1 status")
                return {"msg": "Email send returned non-1 status"}
        except Exception as exc:
            logger.error("SMTP send error: %s", exc)
            return {"msg": "SMTP send error"}

    except Exception as exc:            # template missing or syntax error
        logger.error("Template render failed, falling back to raw HTML: %s", exc)

    # ----------------------------------------------------------------


@webhook_handler()
def whatsapp_template_sender(payload, headers, content_type, cfg):

    config = get_tenant_config(cfg.tenant)
    try:
        if config.whatsapp_integration_enabled:
            wa = WhatsappBusinessClient(config)

            template_id = payload.get("template_id")
            template = wa.template_details(template_id)

            requirements = template_requirements(template)
            batch = payload.get("values")

            # print("requerimientos -------")
            # print(requirements)

            if type(batch) is dict:
                batch = [batch,]

            for template_vars in batch:
                print("valores------------")
                print(template_vars)

                if template_vars.get("document_link", None):
                    document_link = template_vars.get("document_link")
                    if document_link == "attachment":
                        document_link = payload["files"]["attachment"]["url"]
                        template_vars["document_link"] = document_link

                if template_vars.get("image_link", None):
                    image_link = template_vars.get("image_link")
                    if image_link == "attachment":
                        image_link = payload["files"]["attachment"]["url"]
                        template_vars["image_link"] = image_link

                template_object = replace_template_placeholders(requirements, template_vars)
                namespace = wa.retrieve_template_namespace()

                whatsapp_number = template_vars.get("whatsapp_number")
                msg = compose_template_based_message(template,
                                                     phone=whatsapp_number,
                                                     namespace=namespace,
                                                     components=template_object)

                # print("mensaje para enviar:", msg)
                try:
                    send_result = wa.send_message(msg, "template")
                    if isinstance(send_result, dict) and send_result.get("success"):
                        return {"msg": "enviado"}
                    else:
                        error = send_result.get("error", "unknown") if isinstance(send_result, dict) else "no enviado"
                        return {"msg": f"no enviado: {error}"}

                except Exception as exc:
                    return {"msg": f"error: {exc}"}
    except Exception as exc:
        logger.error("Whatsapp send error: %s", exc)
        return {"msg": exc.__str__()}


@webhook_handler()
def communications_template_sender(payload, headers, content_type, cfg):

    # config = TenantConfiguration.objects.get(tenant=cfg.tenant)
    if payload.get("message_type") == "whatsapp":

        whatsapp_template_sender(payload, headers, content_type, cfg)

    elif payload.get("message_type") == "email":

        email_template_sender(payload, headers, content_type, cfg)


@webhook_handler()
def mercado_pago_notifications(payload, headers, content_type, cfg):

    print("type:", payload.get("type",""))
    print("action:", payload.get("action", ""))
    print("date_created:", payload.get("date_created", ""))
    print("data:", payload.get("data", ""))

    return "handled it like a champion"


import base64
import io
import numpy as np
from PIL import Image
# import face_recognition
from crm.models import Contact
from crm.models import FaceDetection


SIM_THR = 0.55


@webhook_handler()
def face_search(payload, headers, content_type, cfg):
    """
    1) extract face embedding
    2) try Contact table
    3) else try FaceDetection table
    4) else create new FaceDetection row
    """
    img_b64 = payload.get("img_b64")
    if not img_b64:
        return {"error": "No image provided"}

    # ---------- decode & store the still image --------------------------------
    raw   = base64.b64decode(img_b64)
    image = Image.open(io.BytesIO(raw))
    npimg = np.array(image)

    # ---------- embedding ------------------------------------------------------
    enc = None #face_recognition.face_encodings(npimg)
    if not enc:
        return {"error": "No face found"}
    emb = enc[0].tolist()                            # plain python list

    # save file once; we may need it anyway
    fname = f"{cfg.tenant.nombre}/faces/{uuid.uuid4().hex}.jpg"
    file_path = default_storage.save(fname, ContentFile(raw))

    # ---------- search Face ---------------------------------------
    face_hit = (
        Face.objects
        .filter(tenant=cfg.tenant)
        .exclude(embedding__isnull=True)  # ← keeps only valid vectors
        .annotate(dist=L2Distance("embedding", emb))
        .order_by("dist")
        .first()
    )

    if face_hit and face_hit.dist is not None and face_hit.dist < SIM_THR:
        # update stats
        face_hit.seen      += 1
        face_hit.last_seen  = timezone.now()
        face_hit.save(update_fields=["seen", "last_seen"])

        person = face_hit.contact.fullname if face_hit and face_hit.contact else "unknown"

        FaceDetection.objects.create(
            image=file_path,
            embedding=emb,
            face = face_hit,
            distance = float(face_hit.dist),
            tenant=cfg.tenant,
        )
        return {
            "match": True,
            "kind":  "face_detection",
            "fd_id": face_hit.id,
            "seen":  face_hit.seen,
            "last_seen": face_hit.last_seen,
            "person": person,
            "image": default_storage.url(file_path),
            "distance": float(face_hit.dist),
        }

    # ---------- 3. nothing found -> store brand-new Face -------------
    fd = Face.objects.create(
        image     = file_path,
        embedding = emb,
        seen      = 1,
        last_seen = timezone.now(),
        contact   = None,
        tenant = cfg.tenant,
    )
    return {
        "match": False,
        "kind":  "new_face_detection",
        "fd_id": fd.id,
        "image": default_storage.url(file_path),
        "distance": None,
    }


@webhook_handler()
def multi_face_search(payload, headers, content_type, cfg):
    """
    Accepts one still frame (base-64) that may contain **multiple faces**.
    For each detected face:
        1) search Contact
        2) else search FaceDetection
        3) else insert new FaceDetection
    Returns: list[dict]  (one result per face)
    """
    img_b64 = payload.get("img_b64")
    if not img_b64:
        return {"error": "No image provided"}

    # ---------- decode --------------------------------------------------------
    raw = base64.b64decode(img_b64)
    image = Image.open(io.BytesIO(raw)).convert("RGB")  # ensure 3-channel
    npimg = np.array(image)

    # ---------- locate & embed all faces -------------------------------------
    boxes = None # face_recognition.face_locations(npimg, model="hog")  # or "cnn"
    encs = None # face_recognition.face_encodings(npimg, boxes)
    if not encs:
        return {"error": "No face found"}

    tenant_folder = f"{cfg.tenant.nombre}/faces/{uuid.uuid4().hex}"
    results = []

    for idx, (emb_vec, box) in enumerate(zip(encs, boxes), start=1):
        emb = emb_vec.tolist()  # JSON-serialisable
        top, right, bottom, left = box

        # ---- Crop & save this individual face (optional) --------------------
        crop = Image.fromarray(npimg[top:bottom, left:right])

        buffer = io.BytesIO()
        crop.save(buffer, format="JPEG", quality=90)
        buffer.seek(0)  # rewind to first byte

        fname = f"{tenant_folder}_{idx}.jpg"
        path = default_storage.save(fname, ContentFile(buffer.getvalue()))


        # ---- 1. Face search ---------------------------------------
        face_hit = (
            Face.objects
            .filter(tenant=cfg.tenant)
            .exclude(embedding__isnull=True)
            .annotate(dist=L2Distance("embedding", emb))
            .order_by("dist")
            .first()
        )
        if face_hit and face_hit.dist is not None and face_hit.dist < SIM_THR:
            face_hit.seen += 1
            face_hit.last_seen = timezone.now()
            face_hit.save(update_fields=["seen", "last_seen"])

            FaceDetection.objects.create(
                image=path,
                embedding=emb,
                face=face_hit,
                distance=float(face_hit.dist),
                tenant=cfg.tenant,
            )

            person = face_hit.contact.fullname if face_hit.contact else "unknown"
            event_detail = {
                "match": True,
                "kind": "face_recognition",
                "fd_id": face_hit.id,
                "seen": face_hit.seen,
                "last_seen": face_hit.last_seen,
                "person": person,
                "distance": float(face_hit.dist),
                "image": default_storage.url(path),
            }
            results.append(event_detail)

            continue

        # ---- 3. insert new Face -----------------------------------
        fd = Face.objects.create(
            tenant=cfg.tenant,
            image=path,
            embedding=emb,
            seen=1,
            last_seen=timezone.now(),
            contact=None,
        )
        event_detail = {
            "match": False,
            "kind": "new_face_detection",
            "fd_id": fd.id,
            "image": default_storage.url(path),
            "distance": None,
        }
        results.append(event_detail)

    return {"faces": results}


# ===============================================================================
# SHOPIFY WEBHOOK HANDLERS
# ===============================================================================

@webhook_handler("shopify_webhook")
def shopify_webhook_handler(payload, headers, content_type, cfg):
    """
    Handle Shopify webhooks for real-time data synchronization.

    Receives data from Shopify (source of truth) and syncs into CRM tables.
    Supports products, customers, and orders webhook topics.
    Routes to appropriate async processing task.
    """
    try:
        # Extract topic from headers
        topic = headers.get('X-Shopify-Topic', '')
        shop_domain = headers.get('X-Shopify-Shop-Domain', '')

        if not topic:
            logger.error("Shopify webhook missing X-Shopify-Topic header")
            return {"status": "error", "message": "Missing topic header"}

        logger.info(f"Processing Shopify webhook: topic={topic}, shop={shop_domain}")

        # Validate webhook signature if secret is configured
        # Note: Shopify webhook signature validation would go here

        # Queue async processing
        from django_celery_results.models import TaskResult

        task = process_shopify_webhook.delay(
            payload=payload,
            headers=dict(headers),  # Convert to dict for serialization
            tenant_code=cfg.tenant.tenant_code,
            topic=topic
        )

        logger.info(f"Queued Shopify webhook processing: task_id={task.id}")

        return {
            "status": "queued",
            "task_id": task.id,
            "topic": topic,
            "shop_domain": shop_domain
        }

    except Exception as e:
        logger.exception(f"Shopify webhook handler failed: {e}")
        return {"status": "error", "message": str(e)}


@webhook_handler("shopify_product_webhook")
def shopify_product_webhook_handler(payload, headers, content_type, cfg):
    """
    Handle Shopify product webhooks (create/update/delete).

    Receives product changes from Shopify (source of truth) and syncs into CRM.
    This is a specialized handler that processes product changes immediately
    for better performance on high-volume product updates.
    """
    try:
        topic = headers.get('X-Shopify-Topic', '')

        if topic not in ['products/create', 'products/update', 'products/delete']:
            return {"status": "ignored", "reason": f"unhandled_topic_{topic}"}

        from crm.services.shopify_sync_service import ShopifySyncService
        from central_hub.integrations.models import IntegrationConfig

        # Find enabled Shopify integration for this tenant
        shopify_configs = IntegrationConfig.get_enabled_for_tenant(cfg.tenant, 'shopify')
        if not shopify_configs:
            logger.warning(f"No enabled Shopify integration found for tenant {cfg.tenant}")
            return {"status": "skipped", "reason": "no_integration"}

        # Use the first enabled config
        config_obj = shopify_configs.first()
        sync_service = ShopifySyncService(cfg.tenant, config_obj.config)

        if topic == 'products/delete':
            # Handle product deletion
            shopify_id = str(payload.get('id', ''))
            try:
                shopify_product = ShopifyProduct.objects.get(
                    tenant=cfg.tenant,
                    shopify_id=shopify_id
                )
                if shopify_product.product:
                    # Mark as inactive instead of deleting
                    shopify_product.sync_status = 'archived'
                    shopify_product.save()
                return {"status": "processed", "action": "archived"}
            except ShopifyProduct.DoesNotExist:
                return {"status": "skipped", "reason": "product_not_found"}

        else:
            # Handle create/update
            result = sync_service._sync_single_product(payload)
            return {"status": "processed", "action": result['action']}

    except Exception as e:
        logger.exception(f"Shopify product webhook handler failed: {e}")
        return {"status": "error", "message": str(e)}


@webhook_handler("shopify_order_webhook")
def shopify_order_webhook_handler(payload, headers, content_type, cfg):
    """
    Handle Shopify order webhooks (create/update/cancelled).

    Receives order changes from Shopify (source of truth) and syncs into CRM.
    Specialized handler for order processing with priority handling.
    """
    try:
        topic = headers.get('X-Shopify-Topic', '')

        if topic not in ['orders/create', 'orders/update', 'orders/cancelled', 'orders/fulfilled']:
            return {"status": "ignored", "reason": f"unhandled_topic_{topic}"}

        from crm.services.shopify_sync_service import ShopifySyncService
        from central_hub.integrations.models import IntegrationConfig

        # Find enabled Shopify integration for this tenant
        shopify_configs = IntegrationConfig.get_enabled_for_tenant(cfg.tenant, 'shopify')
        if not shopify_configs:
            logger.warning(f"No enabled Shopify integration found for tenant {cfg.tenant}")
            return {"status": "skipped", "reason": "no_integration"}

        # Use the first enabled config
        config_obj = shopify_configs.first()
        sync_service = ShopifySyncService(cfg.tenant, config_obj.config)

        result = sync_service._sync_single_order(payload)
        return {"status": "processed", "action": result['action'], "topic": topic}

    except Exception as e:
        logger.exception(f"Shopify order webhook handler failed: {e}")
        return {"status": "error", "message": str(e)}