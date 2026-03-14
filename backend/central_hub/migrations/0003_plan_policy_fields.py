from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("central_hub", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="entitlement_policy",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Plan policy (trial/grace durations, assignment limits, module constraints).",
            ),
        ),
        migrations.AddField(
            model_name="plan",
            name="pricing_policy",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Pricing configuration (base fees, per-unit pricing, included units, currency).",
            ),
        ),
    ]
