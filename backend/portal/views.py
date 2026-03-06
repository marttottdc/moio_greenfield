import asyncio
import http.client
import json
import random

import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET
from django.views.generic import DetailView

from chatbot.lib.whatsapp_client_api import get_customers_waba_id, get_waba_customer_account, get_customer_waba_phone_numbers, \
    subscribe_to_webhooks, register_waba_phone_number, waba_temp_token_swap
from chatbot.models.agent_configuration import AgentConfiguration

from moio_platform.lib.moio_assistant_functions import get_available_tools
from moio_platform.lib.openai_gpt_api import MoioOpenai, AssistantManager, ASSISTANT_TOOL_TYPES
from portal.context_utils import current_tenant
from portal.forms import TenantForm, OpenaiIntegrationConfigForm, PsigmaIntegrationConfigForm, \
    GoogleIntegrationConfigForm
from portal.content_blocks import (
    get_visible_blocks_queryset,
    render_blocks as render_block_group,
)
from portal.models import (
    AppConfig,
    AppMenu,
    MoioUser,
    PortalConfiguration,
    Tenant,
    TenantConfiguration,
)
import logging

User = get_user_model()

logger = logging.getLogger(__name__)


def home(request):
    try:
        tenant = current_tenant.get()
        apps = AppConfig.objects.filter(tenants=tenant)
        sub_menu = AppMenu.objects.filter(app__in=apps.values("name"))

        context = {
            "apps": apps,
            "sub_menu": sub_menu,
            "tenant": tenant,
        }

        partial_template = 'crm/dashboard.html'
        if request.headers.get("HX-Request") == "true":
            return render(request, 'crm/dashboard.html', context=context)

        else:
            # context["load_page"] = 'crm/dashboard.html'
            context["partial_template"] = partial_template
            return render(request, 'layout.html', context=context)

    except Exception as e:
        print(e)
        return http.client.BAD_REQUEST


def moio(request):
    host = request.get_host()
    print("Host:", host)
    #print("Request Headers:", request.headers)
    #print("Request Meta:", request.META)
    #referrer = request.META.get('HTTP_REFERER')
    #print("Referrer URL:", referrer)

    return render(request, template_name='landing.html', context={})


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    template_name = 'users/user_detail.html'
    context_object_name = 'user'

    def get_object(self):
        return self.request.user


@permission_required('users.list_users')
def user_list(request):

    users = MoioUser.objects.filter(tenant=current_tenant.get())
    context = {
        'users': users,
    }

    return render(request,
                  template_name='users/users_list.html',
                  context=context)


@sensitive_post_parameters()
def server_error(request, *args, **kwargs):
    return render(request, '500.html', status=500)


@login_required
def configure_tenant(request):

    forms = {
        'openai_config_form': OpenaiIntegrationConfigForm(),
        'psigma_config_form': PsigmaIntegrationConfigForm(),
        'google_config_form': GoogleIntegrationConfigForm(),
    }

    return render(request,
                  template_name='portal/tenant_config.html',
                  context={'forms': forms})


def build_whatsapp_configuration(request):

    # Define the URL and the parameters
    url = "https://graph.facebook.com/v19.0/me"
    params = {
        'fields':
        'id,name,token_for_business,accounts{whatsapp_number,app_id},ids_for_apps{app,id}',
        'access_token':
'EAAKGM7yIKkoBO3CZAeh8nhZAfwnZCjfnRKh4qTVVZAxUbJt2WzmwIiVa5uZAq3EiaCZAm1ZCGBjnd2ZACuw3pAD3AKrg2551FSDA5eEWcjgk401fs9Qy1OArP8tpZAbxSnGZAACyuW3MX9BBzX5Pon8eVPUY6YlSenhruHtZAhPvk58fWqwZAfyy7ZB2bSwZB9DQh4LsUCy1aCaiCrgHQvacoZD'
    }

    # Make the GET request
    response = requests.get(url, params=params)

    # Print the response status code and content
    print(f"Status Code: {response.status_code}")
    print("Response:")
    print(response.text)


# ========================= CONFIGURATION =================================


@login_required()
def settings(request, state=None):
    context = {}

    partial_template = 'crm/settings.html'
    if request.headers.get("HX-Request") == "true":
        return render(request,
                      template_name='crm/settings.html',
                      context=context)
    else:
        #context["load_page"] = request.path
        context["partial_template"] = partial_template
        return render(request, 'layout.html', context=context)


@login_required
def update_settings(request):

    print(request.POST.get("woocommerce-config-url", None))
    print(request.POST.get("woocommerce-consumer-key", None))
    print(request.POST.get("woocommerce-consumer-secret", None))

    return HttpResponse(
        status=204,
        headers={'HX-Trigger': json.dumps({"showMessage": f"recibido"})})


@login_required()
def configure_openai(request):
    tenant = current_tenant.get()
    config = TenantConfiguration.objects.get(tenant=tenant)

    if request.method == "POST":
        if request.POST.get('enabled') == 'on':
            enabled = True
        else:
            enabled = False

        api_key = request.POST.get('api_key')
        max_retries = request.POST.get('max_retries')
        default_model = request.POST.get('default_model')

        config.openai_integration_enabled = enabled
        config.openai_api_key = api_key
        config.openai_default_model = default_model
        config.openai_max_retries = max_retries
        config.save()

        pong = "Disabled"
        if enabled:

            ai = MoioOpenai(api_key=api_key,
                            default_model=default_model,
                            max_retries=max_retries,
                            min_delay=1)
            pong = ai.simple_response(
                "Send me a short welcome, I have just configured the api in Moio.ai"
            )

        return HttpResponse(
            status=204,
            headers={'HX-Trigger': json.dumps({"showMessage": pong})})

    context = {
        'enabled': config.openai_integration_enabled,
        'api_key': config.openai_api_key,
        'max_retries': config.openai_max_retries,
        'default_model': config.openai_default_model,
    }

    return render(request,
                  template_name='integrations/openai_configuration.html',
                  context=context)


@login_required()
def configure_agent(request, agent_id=None):

    tenant = current_tenant.get()
    config = tenant.configuration.first()

    available_agents = AgentConfiguration.objects.get(tenant=tenant)

    active_tools = []
    assistant = None

    if request.method == "POST":

        asst_model = request.POST.get('assistant_model')
        asst_description = request.POST.get('assistant_description')
        asst_instructions = request.POST.get('assistant_instructions')
        asst_name = request.POST.get('assistant_name')

        tool_collection = []
        for at in ASSISTANT_TOOL_TYPES:
            if request.POST.get(at["type"]) == 'on':
                tool_collection.append({"type": at["type"]})

        for funct in get_available_tools():
            if request.POST.get(funct["function"]["name"]) == 'on':
                tool_collection.append(funct)

        if agent_id is None:

            new_agent = AgentConfiguration.objects.create(
                name=asst_name,
                description=asst_description,
                instructions=asst_instructions,
                model=asst_model,
                selected_tools=tool_collection)
            new_agent.save()

        else:
            print(f"Update assistant {agent_id}")

            assistant = AgentConfiguration.objects.update(
                name=asst_name,
                assistant_id=agent_id,
                selected_tools=tool_collection,
                model=asst_model,
                instructions=asst_instructions,
                description=asst_description)
            if assistant:
                for t in assistant.tools:
                    active_tools.append(t.function.name)

        context = {
            'available_agents': available_agents,
            'assistant_details': assistant,
            'tool_types': ASSISTANT_TOOL_TYPES,
            'available_functions': get_available_tools(),
            'active_tools': active_tools,
            'models': ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        }

        return render(request,
                      template_name='agents/partials/agent_details.html',
                      context=context)

    elif request.method == "GET":

        if agent_id is not None:
            agent = AgentConfiguration.objects.get(id=agent_id)

            if agent:
                for t in agent.tools:
                    active_tools.append(t.function.name)

        else:
            print("Create agent")

    context = {
        'available_agents': available_agents,
        'agent_details': agent,
        'tool_types': ASSISTANT_TOOL_TYPES,
        'available_functions': get_available_tools(),
        'active_tools': active_tools,
        'models': ""
    }
    print(get_available_tools())
    return render(request,
                  template_name='integrations/partials/assistant_details.html',
                  context=context)


@login_required()
def agent_configuration_panel(request):

    tenant = current_tenant.get()
    config = tenant.configuration.first()
    available_assistants = None

    if config.openai_integration_enabled:

        ai = AssistantManager(config=config)
        available_assistants = ai.list_assistants()

    context = {
        'available_assistants': available_assistants,
    }

    return render(request,
                  template_name='agents/agent_configuration_panel.html',
                  context=context)


@login_required()
def configure_assistant(request, assistant_id=None):

    tenant = current_tenant.get()
    config = tenant.configuration.first()

    ai = AssistantManager(config=config)
    available_assistants = ai.list_assistants()
    active_tools = []
    assistant = None

    if request.method == "POST":

        asst_model = request.POST.get('assistant_model')
        asst_description = request.POST.get('assistant_description')
        asst_instructions = request.POST.get('assistant_instructions')
        asst_name = request.POST.get('assistant_name')

        tool_collection = []
        for at in ASSISTANT_TOOL_TYPES:
            if request.POST.get(at["type"]) == 'on':
                tool_collection.append({"type": at["type"]})

        for funct in get_available_tools():
            if request.POST.get(funct["function"]["name"]) == 'on':
                tool_collection.append(funct)

        if assistant_id is None:

            ai.create_assistant(name=asst_name,
                                description=asst_description,
                                instructions=asst_instructions,
                                model=asst_model,
                                selected_tools=tool_collection)

        else:
            print(f"Update assistant {assistant_id}")

            assistant = ai.update_assistant(name=asst_name,
                                            assistant_id=assistant_id,
                                            selected_tools=tool_collection,
                                            model=asst_model,
                                            instructions=asst_instructions,
                                            description=asst_description)
            if assistant:
                for t in assistant.tools:
                    active_tools.append(t.function.name)

        context = {
            'available_assistants': available_assistants,
            'assistant_details': assistant,
            'tool_types': ASSISTANT_TOOL_TYPES,
            'available_functions': get_available_tools(),
            'active_tools': active_tools,
            'models': ai.get_models()
        }

        return render(
            request,
            template_name='integrations/partials/assistant_details.html',
            context=context)

    elif request.method == "GET":

        if assistant_id is not None:
            assistant = ai.get_assistant(assistant_id)

            if assistant:
                for t in assistant.tools:
                    active_tools.append(t.function.name)

        else:
            print("Create assistant")

    context = {
        'available_assistants': available_assistants,
        'assistant_details': assistant,
        'tool_types': ASSISTANT_TOOL_TYPES,
        'available_functions': get_available_tools(),
        'active_tools': active_tools,
        'models': ai.get_models()
    }
    print(get_available_tools())
    return render(request,
                  template_name='integrations/partials/assistant_details.html',
                  context=context)


@login_required()
def assistant_configuration(request):

    tenant = current_tenant.get()
    config = tenant.configuration.first()
    available_assistants = None

    if config.openai_integration_enabled:

        ai = AssistantManager(config=config)
        available_assistants = ai.list_assistants()

    context = {
        'available_assistants': available_assistants,
    }

    return render(request,
                  template_name='integrations/assistant_configuration.html',
                  context=context)


@login_required()
def configure_whatsapp_business(request, state=None):

    portal_config = PortalConfiguration.objects.first()

    tenant = current_tenant.get()
    config = tenant.configuration.first()

    app_id = portal_config.fb_moio_bot_app_id
    callback_uri = f'{portal_config.my_url}fb_oauth_callback/'
    app_config = portal_config.fb_moio_bot_configuration_id
    state_check = request.session.session_key
    access_token = config.whatsapp_token

    waba_config = {
        "whatsapp_integration_enabled": config.whatsapp_integration_enabled,
        "whatsapp_token": config.whatsapp_token,
        "whatsapp_url": config.whatsapp_url,
        "whatsapp_phone_id": config.whatsapp_phone_id,
        "whatsapp_business_account_id": config.whatsapp_business_account_id,
        "whatsapp_name": config.whatsapp_name,
        "whatsapp_catalog_id": config.whatsapp_catalog_id
    }

    extras = {
        'feature': 'whatsapp_embedded_signup',
        'sessionInfoVersion': 3,
        'setup': {
            'business': {
                'name': config.tenant.nombre,
                'email': request.user.email,
                'phone': {
                    'code': 598,
                    'number': '11111111'
                },
                'website': 'https://www.cool.com',
                'address': {
                    'streetAddress1': 'Av Rivera',
                    'city': 'Montevideo',
                    'state': 'MO',
                    'zipPostal': '11600',
                    'country': 'UY'
                },
                'timezone': 'UTC-08:00'
            },
            'phone': {
                'displayName': 'Cool Inc',
                'category': 'FINANCE',
                'description': 'The best finance company.',
            }
        }
    }

    if request.method == "GET":

        error = request.GET.get('error', '')
        code = request.GET.get('code', '')

        if error != '':
            error_msg = request.GET.get('error_description', '')
            error_code = request.GET.get('error_code', '')
            error_reason = request.GET.get('error_reason', '')

        elif code != '':

            print('Requesting token exchange')
            url = 'https://graph.facebook.com/v21.0/oauth/access_token'

            params = {
                'client_id': app_id,
                'client_secret': portal_config.fb_moio_bot_app_secret,
                'redirect_uri': callback_uri,
                'code': code
            }

            response = requests.get(url, params=params)

            if response.status_code == 200:
                access_token = response.json()['access_token']
                token_type = response.json()['token_type']
                expires_in = response.json()['expires_in']

                config.whatsapp_integration_enabled = True
                config.whatsapp_token = access_token
                config.save()

        context = {
            'app_id':
            app_id,
            'callback_uri':
            callback_uri,
            'app_config':
            app_config,
            'state_check':
            state_check,
            'access_token':
            access_token,
            'extras':
            extras,
            "waba_config":
            waba_config,
            'auth_url':
            f"https://www.facebook.com/v21.0/dialog/oauth?client_id={app_id}&redirect_uri={callback_uri}&config_id={app_config}&state={state_check}&response_type=code&extras={extras}"
        }

        return render(
            request,
            template_name=
            'settings/integrations/whatsapp_business_configuration.html',
            context=context)


@csrf_exempt
def facebook_oauth_callback_handler(request):

    logger.info("called oauth_callback_handler")

    if request.method == "GET":
        try:
            error = request.GET.get('error')
            code = request.GET.get('code', '')
            state = request.GET.get('state', '')
            action = request.GET.get('action', '')
            message = ""

            if error:

                context = {
                    "error_msg": request.GET.get('error_description', ''),
                    "error_code": request.GET.get('error_code', ''),
                    "error_reason": request.GET.get('error_reason', '')
                }

                return render(request,
                              'settings/integrations/waba_success.html',
                              context=context)

            elif code:

                portal_config = PortalConfiguration.objects.first()
                access_token = waba_temp_token_swap(code, portal_config)

                customer_waba_id = get_customers_waba_id(access_token)
                waba_customer_data = get_waba_customer_account(
                    customer_waba_id)
                phone_numbers = get_customer_waba_phone_numbers(
                    customer_waba_id)

                context = {
                    "message": f"Token Obtained !",
                    "access_token": access_token,
                    "waba_customer_data": waba_customer_data,
                    "phone_numbers": phone_numbers,
                }

                return render(request,
                              'settings/integrations/waba_success.html',
                              context=context)

            else:
                logger.error("no path")
                portal_config = PortalConfiguration.objects.first()

                access_token = request.GET.get("access_token")
                display_phone_number = request.GET.get("display_phone_number")
                phone_status = request.GET.get("phone_status")
                whatsapp_name = request.GET.get("whatsapp_name")
                whatsapp_phone_id = request.GET.get("whatsapp_phone_id")
                waba_customer_id = request.GET.get("waba_customer_id")
                waba_customer_name = request.GET.get("waba_customer_name")
                waba_business_id = request.GET.get("waba_business_id")
                waba_business_name = request.GET.get("waba_business_name")

                waba_customer_data = get_waba_customer_account(
                    waba_customer_id)
                phone_numbers = get_customer_waba_phone_numbers(
                    waba_customer_id)

                context = {
                    "access_token": access_token,
                    "waba_customer_data": waba_customer_data,
                    "phone_numbers": phone_numbers,
                }

                return render(request,
                              'settings/integrations/waba_success.html',
                              context=context)

        except Exception as e:
            logger.exception(e)
            return HttpResponse("Server error", status=500)


@login_required
def confirm_waba_configuration(request):

    if request.method == "POST":

        access_token = request.POST.get("access_token")
        display_phone_number = request.POST.get("display_phone_number")
        phone_status = request.POST.get("phone_status")
        whatsapp_name = request.POST.get("whatsapp_name")
        whatsapp_phone_id = request.POST.get("whatsapp_phone_id")
        waba_customer_id = request.POST.get("waba_customer_id")
        waba_customer_name = request.POST.get("waba_customer_name")
        waba_business_id = request.POST.get("waba_business_id")
        waba_business_name = request.POST.get("waba_business_name")

        tenant = current_tenant.get()
        config = tenant.configuration.first()
        portal_config = PortalConfiguration.objects.first()

        try:
            config.whatsapp_integration_enabled = True
            config.whatsapp_token = access_token
            config.whatsapp_business_account_id = waba_customer_id
            config.whatsapp_name = whatsapp_name
            config.whatsapp_phone_id = whatsapp_phone_id
            config.whatsapp_url = "https://graph.facebook.com/v21.0/"

            config.save()

        except Exception as e:
            logger.exception(e)

        response_subscribing_webhooks = subscribe_to_webhooks(
            waba_customer_id, portal_config.fb_system_token)
        response_registering_phone = register_waba_phone_number(
            whatsapp_phone_id, portal_config.fb_system_token)

        logger.info(response_registering_phone)

        context = {
            "phone_status": phone_status,
            "response_subscribing_webhooks": response_subscribing_webhooks,
            "response_phone_register": response_registering_phone,
        }

        return render(
            request,
            'settings/integrations/partials/waba_registration_results.html',
            context=context)


@csrf_exempt
def instagram_oauth_callback_handler(request):
    print("called oauth_callback_handler")
    print(request.method)


@csrf_exempt
def facebook_revoke_access(request):

    return HttpResponse(200)


@csrf_exempt
def facebook_data_removal(request):

    return HttpResponse(200)


# ======================== ADMINISTRATION =================================


@login_required()
def admin_tenants(request):
    if request.user.is_superuser:

        return render(request,
                      template_name="administration/administration.html",
                      context={})


@login_required()
def admin_users(request):
    if request.user.is_superuser:

        return render(request,
                      template_name="administration/admin_users.html",
                      context={})


@login_required
def add_tenant(request):

    if not request.user.is_superuser:
        return render(request, template_name="404.html", context={})

    if request.method == "POST":

        tenant_form = TenantForm(request.POST)

        if tenant_form.is_valid():

            tenant_form.save()

            tenants = Tenant.objects.all()

            return render(
                request,
                template_name='administration/partials/tenant_form.html',
                context={
                    'tenant_form': tenant_form,
                    'tenants': tenants
                })

        else:
            return HttpResponse(
                status=204,
                headers={
                    'HX-Trigger':
                    json.dumps({"showMessage": f"{tenant_form.errors} "})
                })

    else:
        tenant_form = TenantForm()
        tenants = Tenant.objects.all()

        return render(request,
                      template_name='administration/partials/tenant_form.html',
                      context={
                          'tenant_form': tenant_form,
                          'tenants': tenants
                      })


async def sse_stream(request):

    if request.user.is_authenticated:

        async def event_stream():

            while True:
                yield f'data: {timezone.now()}\n\n'

                await asyncio.sleep(60)

        return StreamingHttpResponse(event_stream(),
                                     content_type='text/event-stream')


def health_check(request):

    return HttpResponse("I'm Good", status=200)


@login_required
def admin_console(request):
    """SaaS Management Console - Superuser only"""
    if not request.user.is_superuser:
        return render(request,
                      template_name="403.html",
                      context={},
                      status=403)

    # Get statistics
    tenants = Tenant.objects.all()
    users = MoioUser.objects.all()
    portal_config = PortalConfiguration.objects.first()

    context = {
        'tenants': tenants,
        'users': users,
        'portal_config': portal_config,
        'total_tenants': tenants.count(),
        'active_tenants': tenants.filter(enabled=True).count(),
        'total_users': users.count(),
    }

    partial_template = 'portal/admin_console.html'
    if request.headers.get("HX-Request") == "true":
        return render(request, template_name=partial_template, context=context)
    else:
        context["partial_template"] = partial_template
        return render(request, 'layout.html', context=context)


@login_required
def admin_tenant_form(request):
    """Handle tenant creation and editing forms"""
    if not request.user.is_superuser:
        return HttpResponse("Forbidden", status=403)

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        domain = request.POST.get('domain')
        enabled = request.POST.get('enabled') == 'on'

        tenant = Tenant.objects.create(nombre=nombre,
                                       domain=domain,
                                       enabled=enabled)

        # Create default configuration for the tenant
        TenantConfiguration.objects.create(tenant=tenant)

        # Return updated tenant list
        tenants = Tenant.objects.all()
        return render(request, 'portal/partials/tenant_list.html',
                      {'tenants': tenants})

    return render(request, 'portal/partials/tenant_form.html')


@login_required
def admin_tenant_edit(request, tenant_id):
    """Handle tenant editing"""
    if not request.user.is_superuser:
        return HttpResponse("Forbidden", status=403)

    tenant = Tenant.objects.get(pk=tenant_id)

    if request.method == 'POST':
        tenant.nombre = request.POST.get('nombre')
        tenant.domain = request.POST.get('domain')
        tenant.enabled = request.POST.get('enabled') == 'on'
        tenant.save()

        # Return updated tenant list
        tenants = Tenant.objects.all()
        return render(request, 'portal/partials/tenant_list.html',
                      {'tenants': tenants})

    return render(request, 'portal/partials/tenant_form.html',
                  {'tenant': tenant})


@login_required
def admin_tenant_toggle(request, tenant_id):
    """Toggle tenant status"""
    if not request.user.is_superuser:
        return HttpResponse("Forbidden", status=403)

    tenant = Tenant.objects.get(pk=tenant_id)
    tenant.enabled = not tenant.enabled
    tenant.save()

    # Return updated tenant list
    tenants = Tenant.objects.all()
    return render(request, 'portal/partials/tenant_list.html',
                  {'tenants': tenants})


@login_required
def admin_system_config(request):
    """Handle system configuration updates"""
    if not request.user.is_superuser:
        return HttpResponse("Forbidden", status=403)

    if request.method == 'POST':
        portal_config = PortalConfiguration.objects.first()
        if not portal_config:
            portal_config = PortalConfiguration.objects.create()

        portal_config.site_name = request.POST.get('site_name', '')
        portal_config.company = request.POST.get('company', '')
        portal_config.my_url = request.POST.get('my_url', '')
        portal_config.whatsapp_webhook_token = request.POST.get(
            'whatsapp_webhook_token', '')
        portal_config.fb_system_token = request.POST.get('fb_system_token', '')
        portal_config.save()

        return HttpResponse(status=204,
                            headers={
                                'HX-Trigger':
                                json.dumps({
                                    "showMessage":
                                    "Configuration updated successfully"
                                })
                            })

    return HttpResponse("Method not allowed", status=405)


@require_GET
def content_blocks(request, group: str):
    blocks = get_visible_blocks_queryset(group)
    if not blocks.exists():
        raise Http404("No active content blocks for this group")

    rendered = render_block_group(group)
    response = HttpResponse(rendered)
    if request.headers.get("HX-Request") == "true":
        response['HX-Trigger'] = json.dumps({
            'contentBlocksRendered': group,
        })
    return response


def experience(request):

    context = {}

    return render(request,
                  template_name="experiences/test.html",
                  context=context)
