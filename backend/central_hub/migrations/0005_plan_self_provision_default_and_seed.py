from django.db import migrations, models


DEFAULT_PLAN_ROWS = {
    "free": {
        "name": "Free",
        "display_order": 0,
        "is_active": True,
        "is_self_provision_default": True,
        "pricing_policy": {},
        "entitlement_policy": {
            "features": {
                "crm": True,
                "crm_contacts_read": True,
                "crm_contacts_write": True,
                "campaigns": False,
                "campaigns_read": False,
                "campaigns_send": False,
                "flows": False,
                "flows_read": False,
                "flows_run": False,
                "flows_edit": False,
                "chatbot": False,
                "datalab": False,
                "settings_integrations_manage": False,
                "users_manage": False,
            },
            "limits": {"seats": 5, "agents": 0, "flows": 0},
            "ui": {"module_enablements": {"crm": True, "flowsDatalab": False, "chatbot": False, "agentConsole": False}},
        },
    },
    "pro": {
        "name": "Pro",
        "display_order": 10,
        "is_active": True,
        "is_self_provision_default": False,
        "pricing_policy": {},
        "entitlement_policy": {
            "features": {
                "crm": True,
                "crm_contacts_read": True,
                "crm_contacts_write": True,
                "campaigns": False,
                "campaigns_read": False,
                "campaigns_send": False,
                "flows": True,
                "flows_read": True,
                "flows_run": True,
                "flows_edit": True,
                "chatbot": True,
                "datalab": True,
                "settings_integrations_manage": False,
                "users_manage": True,
            },
            "limits": {"seats": 10, "agents": 3, "flows": 20},
            "ui": {"module_enablements": {"crm": True, "flowsDatalab": True, "chatbot": True, "agentConsole": False}},
        },
    },
    "business": {
        "name": "Business",
        "display_order": 20,
        "is_active": True,
        "is_self_provision_default": False,
        "pricing_policy": {},
        "entitlement_policy": {
            "features": {
                "crm": True,
                "crm_contacts_read": True,
                "crm_contacts_write": True,
                "campaigns": True,
                "campaigns_read": True,
                "campaigns_send": True,
                "flows": True,
                "flows_read": True,
                "flows_run": True,
                "flows_edit": True,
                "chatbot": True,
                "datalab": True,
                "settings_integrations_manage": True,
                "users_manage": True,
            },
            "limits": {"seats": 50, "agents": 10, "flows": 100},
            "ui": {"module_enablements": {"crm": True, "flowsDatalab": True, "chatbot": True, "agentConsole": True}},
        },
    },
}


def seed_plan_rows(apps, schema_editor):
    Plan = apps.get_model("central_hub", "Plan")
    for key, defaults in DEFAULT_PLAN_ROWS.items():
        plan, created = Plan.objects.get_or_create(key=key, defaults=defaults)
        if not created:
            updated = False
            if not getattr(plan, "name", ""):
                plan.name = defaults["name"]
                updated = True
            if not getattr(plan, "pricing_policy", None):
                plan.pricing_policy = defaults["pricing_policy"]
                updated = True
            if not getattr(plan, "entitlement_policy", None):
                plan.entitlement_policy = defaults["entitlement_policy"]
                updated = True
            if key == "free" and not getattr(plan, "is_self_provision_default", False):
                plan.is_self_provision_default = True
                updated = True
            if updated:
                plan.save()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("central_hub", "0004_provisioningjob"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="is_self_provision_default",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(seed_plan_rows, noop_reverse),
    ]
