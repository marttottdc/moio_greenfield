import json
import time

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.checks import messages
from django.db.models import Count
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from user_agents import parse
from django.conf import settings

from chatbot.charts.dahboard_stats import conversations_over_time
from chatbot.core.campaign_flow import AssessmentInstanceFlow
from chatbot.lib.whatsapp_client_api import compose_media_template_message, template_requirements, \
    WhatsappBusinessClient, compose_template_based_message, replace_template_placeholders
from assessments.models.assessment_data import PainPoint, AssessmentCampaign, AssessmentInstance
from chatbot.models.chatbot_session import ChatbotMemory, ChatbotSession

from chatbot.tasks import whatsapp_webhook_handler, archive_conversation, instagram_webhook_handler, messenger_webhook_handler
from crm.models import Contact
from moio_platform.lib.tools import check_elapsed_time
from moio_platform.lib.openai_gpt_api import get_simple_response
from central_hub.context_utils import current_tenant
from central_hub.models import PlatformConfiguration
from central_hub.tenant_config import get_tenant_config

from chatbot.core.assessment_manager import AssessmentManager
import logging

logger = logging.getLogger(__name__)


@csrf_exempt
def whatsapp_webhook_receiver(request):

    if request.method == "GET":
        try:
            portal_config = PlatformConfiguration.objects.first()
            access_token = portal_config.whatsapp_webhook_token
            token = request.GET.get("hub.verify_token")
            challenge = request.GET.get("hub.challenge")

            if token is not None and challenge is not None and token == access_token:
                response = HttpResponse(content=challenge, status=200)
                response['Content-Type'] = 'text/plain'

                return response

            return HttpResponseBadRequest()

        except Exception as e:
            print(e)
            return HttpResponseBadRequest()

    elif request.method == "POST":
        try:
            body = json.loads(request.body)
            job = whatsapp_webhook_handler.apply_async(args=[body,], queue=settings.HIGH_PRIORITY_Q)
            print(f"Sent to worker in job: {job.id}")
            return HttpResponse("EVENT_RECEIVED", status=200)

        except Exception as e:
            print(e)
    return HttpResponseBadRequest()


@csrf_exempt
def instagram_webhook_receiver(request):

    if request.method == "GET":
        try:
            portal_config = PlatformConfiguration.objects.first()
            access_token = portal_config.whatsapp_webhook_token
            token = request.GET.get("hub.verify_token")
            challenge = request.GET.get("hub.challenge")

            if token is not None and challenge is not None and token == access_token:
                response = HttpResponse(content=challenge, status=200)
                response['Content-Type'] = 'text/plain'

                return response

            return HttpResponseBadRequest()

        except Exception as e:
            print(e)
            return HttpResponseBadRequest()

    elif request.method == "POST":
        try:
            body = json.loads(request.body)
            job = instagram_webhook_handler.apply_async(args=[body,], queue=settings.HIGH_PRIORITY_Q)
            print(f"Sent to worker in job: {job.id}")
            return HttpResponse("EVENT_RECEIVED", status=200)

        except Exception as e:
            print(e)
    return HttpResponseBadRequest()


@csrf_exempt
def messenger_webhook_receiver(request):

    if request.method == "GET":
        try:
            portal_config = PlatformConfiguration.objects.first()
            access_token = portal_config.whatsapp_webhook_token
            token = request.GET.get("hub.verify_token")
            challenge = request.GET.get("hub.challenge")

            if token is not None and challenge is not None and token == access_token:
                response = HttpResponse(content=challenge, status=200)
                response['Content-Type'] = 'text/plain'

                return response

            return HttpResponseBadRequest()

        except Exception as e:
            print(e)
            return HttpResponseBadRequest()

    elif request.method == "POST":
        try:
            print(request.body)
            body = json.loads(request.body)
            job = messenger_webhook_handler.apply_async(args=[body,], queue=settings.HIGH_PRIORITY_Q)
            print(f"Sent to worker in job: {job.id}")
            return HttpResponse("EVENT_RECEIVED", status=200)

        except Exception as e:
            print(e)
    return HttpResponseBadRequest()


@login_required()
def list_whatsapp_templates(request):
    tenant = current_tenant.get()
    config = get_tenant_config(tenant)
    portal_config = PlatformConfiguration.objects.first()
    templates = []

    if config.whatsapp_integration_enabled:
        wa = WhatsappBusinessClient(config)

        template_list = wa.download_message_templates()

        if template_list:
            for template in template_list:
                t = {
                    "name": template["name"],
                    "category": template["category"],
                    "id": template["id"],
                    "language": template["language"],
                    "status": template["status"]
                }
                templates.append(t)

        context = {
            "templates": templates,
            "moio_fb_id": portal_config.fb_moio_business_manager_id,
            "waba_id": config.whatsapp_business_account_id,
        }

        return render(request, 'chatbot/watemplates.html', context)
    else:
        return HttpResponse(status=403, message="Whatsapp Integration disabled")


@login_required()
def wa_templates_for_campaigns(request):
    """Endpoint to load WhatsApp templates for campaign creation"""
    tenant = current_tenant.get()
    config = get_tenant_config(tenant)
    templates = []

    if config.whatsapp_integration_enabled:
        wa = WhatsappBusinessClient(config)
        template_list = wa.download_message_templates()

        if template_list:
            for template in template_list:
                if template.get("status") == "APPROVED":  # Only show approved templates
                    t = {
                        "name": template["name"],
                        "category": template["category"],
                        "id": template["id"],
                        "language": template["language"],
                        "status": template["status"]
                    }
                    templates.append(t)

        context = {"templates": templates}
        return render(request, 'crm/partials/whatsapp_templates_list.html', context)
    else:
        return HttpResponse(status=403)


@login_required()
def watemplatedetails(request, template_id):
    tenant = current_tenant.get()
    config = get_tenant_config(tenant)

    if config.whatsapp_integration_enabled:
        wa = WhatsappBusinessClient(config)

        template_detail = wa.download_message_template_detail(template_id)

        # Extract parameter placeholders
        parameters = []
        parameter_format = template_detail.get('parameter_format', 'POSITIONAL')

        for component in template_detail.get('components', []):
            if component['type'] == 'BODY':
                text = component.get('text', '')
                if parameter_format == 'POSITIONAL':
                    # Find {{1}}, {{2}}, etc.
                    import re
                    matches = re.findall(r'\{\{(\d+)\}\}', text)
                    print(f"found r: {matches}")
                    for match in matches:
                        parameters.append(f"{match}")
                elif parameter_format == 'NAMED':
                    # Find {{variable_name}}
                    import re
                    matches = re.findall(r'\{\{([^}]+)\}\}', text)
                    print(f"found r: {matches}")
                    for match in matches:
                        parameters.append(match)

        context = {
            'template': template_detail,
            'parameters': parameters,
            'parameter_format': parameter_format
        }

        # If HTMX request from campaigns modal, return modal content
        if request.headers.get("HX-Request") and 'campaigns' in request.META.get('HTTP_REFERER', ''):
            return render(request, 'campaigns/partials/template_details_modal_content.html', context)

        return render(request, 'chatbot/watemplate_details.html', context)


@login_required()
def whatsapp_template_details(request, template_id):
    tenant = current_tenant.get()
    config = get_tenant_config(tenant)

    if config.whatsapp_integration_enabled:
        wa = WhatsappBusinessClient(config)

        # template = WaTemplate.objects.get(template_id=template_id)
        template = wa.template_details(template_id)

        requirements = template_requirements(template)

        if request.method == "POST":

            vars = request.POST.dict()
            print("requerimientos -------")
            print(requirements)
            print("valores------------")
            print(vars)

            template_object = replace_template_placeholders(requirements, vars)
            print("reemplazo-------")
            print(template_object)
            namespace = wa.retrieve_template_namespace()

            msg = compose_template_based_message(template, phone=vars["whatsapp_number"], namespace=namespace, components=template_object)

            print("mensaje para enviar:", msg)

            send_result = wa.send_message(msg, "template")
            if isinstance(send_result, dict) and send_result.get("success"):
                return HttpResponse(
                    status=204,
                    headers={
                        'HX-Trigger': json.dumps({
                            "showMessage": f"Mensaje enviado"
                        })
                    })
            else:
                error = send_result.get("error", "Error desconocido") if isinstance(send_result, dict) else "Error desconocido"
                return HttpResponse(
                    status=204,
                    headers={
                        'HX-Trigger': json.dumps({
                            "showMessage": f"Mensaje no Enviado: {error}"
                        })
                    })

        else:

            context = {
                'target_template': template,
                'requirements': requirements,
                'contacts': Contact.objects.filter(tenant=config.tenant_id).order_by("fullname", "whatsapp_name"),
            }
            return render(request, 'chatbot/watemplate_details.html', context)
    else:
        HttpResponse(status=500)


@login_required()
def create_campaign(request):

    if request.user.is_authenticated:
        if request.method == "POST":
            print("not ready yet my friend")

        else:
            form = {}

            return render(request, 'chatbot/wa_campaign_target.html', {"form": form})

    else:

        messages.INFO(request, "You Must Be Logged In...")
        return redirect('account/login')


@login_required()
def dashboard(request):
    tenant = current_tenant.get()
    contacts_with_session_count = Contact.objects.annotate(
        session_count=Count('chatbot_session')
    ).filter(session_count__gt=0, tenant=tenant).values('user_id', 'fullname', 'phone', 'session_count')  # Adjust fields as needed

    context = {
        "conversations_over_time": conversations_over_time(tenant, date_range=90),
        "contacts_with_session_count": contacts_with_session_count
    }

    return render(request, 'chatbot/dashboard.html', context=context)


@login_required()
def dashboard_kpi(request):
    active_sessions = ChatbotSession.objects.filter(tenant=current_tenant.get(), active=True).count()

    return render(request, 'chatbot/partials/dashboard_kpis.html', {'active_sessions': active_sessions})


@login_required()
def chatroom(request):
    tenant = current_tenant.get()
    # chat_sessions = ChatbotSession.objects.filter(tenant=tenant).order_by("-active", "-last_interaction", "-start", )
    # active_sessions = chat_sessions.count()

    context = {
        # "active_sessions": active_sessions,
        # "sessions": chat_sessions
    }

    return render(request, template_name='chatbot/chatroom.html', context=context)


@login_required()
def sessions(request):
    start_time = timezone.now()
    tenant = current_tenant.get()
    chat_sessions = ChatbotSession.objects.filter(tenant=tenant, active=True).order_by("-active", "-last_interaction", "-start")
    active_sessions = chat_sessions.count()

    context = {
        "active_sessions": active_sessions,
        "sessions": chat_sessions
    }

    print(check_elapsed_time(start_time, "List of Sessions"))

    return render(request, template_name='crm/communications.html', context=context)


def conversation_detail(request, session_id):

    if request.method == "GET":
        session = ChatbotSession.objects.get(pk=session_id)
        session_thread = session.memory_thread.order_by("created")

        context = {
            "session": session,
            "session_transcript": session_thread,
        }

        return render(request=request, template_name="crm/communications/partials/chat_session_item_details.html", context=context)

    elif request.method == "POST":
        action = request.POST.get("action")
        if action == "archive_conversation":
            print("selected archive conversation")

            archive_conversation.apply_async(args=[str(session_id)], queue=settings.HIGH_PRIORITY_Q)

        return HttpResponse(
            status=204,
            headers={
                'HX-Trigger': json.dumps({
                    "showMessage": f"{action}"
                })
            })


def room(request, room_name):

    return render(request, "chatbot/chatroom.html", {"room_name": room_name})


def send_message(request):
    print(request.POST)
    print(request.POST.get("messageInput"))
    return HttpResponse("200")


@csrf_exempt
def handle_facebook_code(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        # Process the code to obtain the access token, etc.
        print(code)

        return JsonResponse({'status': 'success', 'code': code})
    return JsonResponse({'status': 'failed'}, status=400)

# ===================================================


@csrf_exempt
def self_assessments(request, campaign_id):

    campaign = Campaign.objects.get(pk=campaign_id)
    config = get_tenant_config(campaign.tenant)

    print(f'Request session:{request.session.session_key}')

    user_agent = parse(request.META.get('HTTP_USER_AGENT', ''))
    browser_family = user_agent.browser.family
    browser_version = user_agent.browser.version_string
    device_family = user_agent.device.family
    is_mobile = user_agent.is_mobile
    ip_address = request.META.get('REMOTE_ADDR')

    instance_cookie = request.COOKIES.get('instance')

    if instance_cookie:

        try:
            assessment = AssessmentInstance.objects.get(id=instance_cookie, campaign=campaign)

        except AssessmentInstance.DoesNotExist:

            if request.user.is_authenticated:
                try:
                    assessment = AssessmentInstance.objects.get(user=request.user, campaign=campaign)

                except AssessmentInstance.DoesNotExist:
                    assessment = AssessmentInstance.objects.create(user=request.user, campaign=campaign)
                    assessment.save()
            else:
                assessment = AssessmentInstance.objects.create(campaign=campaign)
                assessment.save()
    else:
        assessment = AssessmentInstance.objects.create(campaign=campaign)
        assessment.save()

    assessment_flow = AssessmentInstanceFlow(assessment)
    print(f'Assessment flow: {assessment_flow.get_status()}')
    assessment.display()

    if request.method == 'POST':
        action = request.POST.get("action", "")
        print(f'action: {action}')

        if action == "search":
            solution_search = request.POST.get("solution_search", "")
            print(f'{solution_search}')

            instruction = f'Eres un sistema de autodiagnostico orientado a encontrar soluciones para problemas estrategicos de las empresas, creado por Estrategio - Consultoría Inteligente. El usuario acaba de decir que necesitas ayuda con: {solution_search}, crea una frase de 150 caracteres para alentarlo, esta frase la responderemos el formulario de autodiagnostico'
            reaction = get_simple_response(prompt=instruction, openai_api_key=config.openai_api_key, model=config.openai_default_model)
            response = render(request, template_name='self_assessment/question_canvas.html', context={"reaction": reaction, "campaign": campaign})
            response.set_cookie('moio-campaigns-instance', assessment.id, max_age=30 * 24 * 60 * 60, httponly=True,
                                secure=True)
            return response

        if action == "load_more":
            pain_points = PainPoint.objects.all().order_by("-created")
            response = render(request, template_name='self_assessment/self_assessment.html', context={"pain_points": pain_points, "campaign": campaign})
            response.set_cookie('moio-campaigns-instance', assessment.id, max_age=30 * 24 * 60 * 60, httponly=True,
                                secure=True)
            return response

    pain_points = PainPoint.objects.all()

    response = render(request, template_name='self_assessment/self_assessment.html', context={"pain_points": pain_points, "campaign": campaign})
    response.set_cookie('instance', assessment.id,  max_age=30*24*60*60, httponly=True, secure=True)
    return response


@csrf_exempt
def assessment(request, campaign_id):

    campaign = Campaign.objects.get(pk=campaign_id)
    instance_cookie = request.COOKIES.get('instance')

    if instance_cookie:

        try:
            assessment_instance = AssessmentInstance.objects.get(id=instance_cookie, campaign=campaign)

        except AssessmentInstance.DoesNotExist:

            if request.user.is_authenticated:
                try:
                    assessment_instance = AssessmentInstance.objects.get(user=request.user, campaign=campaign)

                except AssessmentInstance.DoesNotExist:
                    assessment_instance = AssessmentInstance.objects.create(user=request.user, campaign=campaign)
                    assessment_instance.save()
            else:
                assessment_instance = AssessmentInstance.objects.create(campaign=campaign)
                assessment_instance.save()
    else:
        assessment_instance = AssessmentInstance.objects.create(campaign=campaign)
        assessment_instance.save()

    assessment_manager = AssessmentManager(assessment_instance)
    assessment_instance.display()

    if request.method == 'POST':

        assessment_manager.handle_response(request)
        next_step = assessment_manager.get_next_step()
        context = {
            'object': assessment_manager.get_message(),
            'current_question': next_step,
            'campaign': campaign
        }
        response = render(request, 'assessments/canvas.html', context=context)
        response['HX-Trigger'] = json.dumps({
            "showMessage": f"respuesta recibida. Status {assessment_instance.status}"
        })

        return response

    next_step = assessment_manager.get_next_step()
    context = {
        'object': assessment_manager.get_message(),
        'current_question': next_step,
        'campaign': campaign
    }
    response = render(request, 'assessments/canvas.html', context=context)
    return response


@login_required()
def app(request):
    context = {
        "menu": [],
        "menu_title": "Chatbot",
        "menu_icon": "mdi mdi-chat",
        "default_screen": "dashboard",
        "name": "Chatbot",
    }

    return render(request, template_name='moio_main.html', context=context)


def facebook_flows_handler(request):

    ENCRYPTED_FLOW_DATA = request.body.get("encrypted_flow_data")
    ENCRYPTED_AES_KEY = request.body.get("encrypted_aes_key")
    INITIAL_VECTOR = request.body.get("initial_vector")

    print(ENCRYPTED_FLOW_DATA, ENCRYPTED_AES_KEY, INITIAL_VECTOR)

    return HttpResponse("421")

# ============= DESKTOP AGENT (STUBBED) ===================


@login_required
def desktop_agent(request):
    """Desktop agent view - stubbed, not currently in use."""
    return HttpResponse("Desktop agent feature is not available.", status=501)


@login_required
def desktop_agent_response_stream(request):
    """Desktop agent response stream - stubbed, not currently in use."""
    return HttpResponse("Desktop agent feature is not available.", status=501)


from chatbot.core.whatsapp_flow_handler import data


@csrf_exempt
def flow_handler(request):

    return data(request)

