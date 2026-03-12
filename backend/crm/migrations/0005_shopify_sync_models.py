# Shopify sync models: live in crm app so migrations run on tenant schemas only
# (crm_product, crm_customer, crm_ecommerceorder exist only there).

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0004_add_suggested_activities_to_capture"),
        ("tenancy", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShopifyProduct",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shopify_id", models.CharField(db_index=True, max_length=20, unique=True)),
                ("handle", models.CharField(blank=True, max_length=255)),
                ("product_type", models.CharField(blank=True, max_length=255)),
                ("vendor", models.CharField(blank=True, max_length=255)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_at_shopify", models.DateTimeField(blank=True, null=True)),
                ("updated_at_shopify", models.DateTimeField(blank=True, null=True)),
                ("last_synced", models.DateTimeField(blank=True, null=True)),
                (
                    "sync_status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("archived", "Archived"),
                            ("draft", "Draft"),
                        ],
                        default="active",
                        max_length=20,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenancy.tenant"),
                ),
                (
                    "product",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shopify_data",
                        to="crm.product",
                    ),
                ),
            ],
            options={
                "db_table": "shopify_product",
            },
        ),
        migrations.CreateModel(
            name="ShopifyCustomer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shopify_id", models.CharField(db_index=True, max_length=20, unique=True)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("first_name", models.CharField(blank=True, max_length=255)),
                ("last_name", models.CharField(blank=True, max_length=255)),
                ("phone", models.CharField(blank=True, max_length=50)),
                ("verified_email", models.BooleanField(default=False)),
                ("accepts_marketing", models.BooleanField(default=False)),
                ("tax_exempt", models.BooleanField(default=False)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("addresses", models.JSONField(blank=True, default=list)),
                ("default_address", models.JSONField(blank=True, null=True)),
                ("created_at_shopify", models.DateTimeField(blank=True, null=True)),
                ("updated_at_shopify", models.DateTimeField(blank=True, null=True)),
                ("last_synced", models.DateTimeField(blank=True, null=True)),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenancy.tenant"),
                ),
                (
                    "customer",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shopify_data",
                        to="crm.customer",
                    ),
                ),
            ],
            options={
                "db_table": "shopify_customer",
            },
        ),
        migrations.CreateModel(
            name="ShopifyOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shopify_id", models.CharField(db_index=True, max_length=20, unique=True)),
                ("order_number", models.CharField(blank=True, max_length=20)),
                ("name", models.CharField(blank=True, max_length=50)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=50)),
                ("subtotal_price", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("total_tax", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("total_discounts", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("total_price", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("shipping_address", models.JSONField(blank=True, null=True)),
                ("billing_address", models.JSONField(blank=True, null=True)),
                ("shipping_lines", models.JSONField(blank=True, default=list)),
                ("line_items", models.JSONField(blank=True, default=list)),
                (
                    "financial_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("pending", "Pending"),
                            ("authorized", "Authorized"),
                            ("paid", "Paid"),
                            ("partially_paid", "Partially Paid"),
                            ("refunded", "Refunded"),
                            ("voided", "Voided"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "fulfillment_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("fulfilled", "Fulfilled"),
                            ("partial", "Partial"),
                            ("unfulfilled", "Unfulfilled"),
                        ],
                        max_length=20,
                    ),
                ),
                ("created_at_shopify", models.DateTimeField(blank=True, null=True)),
                ("updated_at_shopify", models.DateTimeField(blank=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("last_synced", models.DateTimeField(blank=True, null=True)),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenancy.tenant"),
                ),
                (
                    "ecommerce_order",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shopify_data",
                        to="crm.ecommerceorder",
                    ),
                ),
            ],
            options={
                "db_table": "shopify_order",
            },
        ),
        migrations.CreateModel(
            name="ShopifySyncLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "sync_type",
                    models.CharField(
                        choices=[
                            ("products", "Products"),
                            ("customers", "Customers"),
                            ("orders", "Orders"),
                        ],
                        max_length=20,
                    ),
                ),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("records_processed", models.IntegerField(default=0)),
                ("records_created", models.IntegerField(default=0)),
                ("records_updated", models.IntegerField(default=0)),
                ("records_failed", models.IntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("partial", "Partial Success"),
                        ],
                        default="running",
                        max_length=20,
                    ),
                ),
                ("error_message", models.TextField(blank=True)),
                ("error_details", models.JSONField(blank=True, default=dict)),
                ("shopify_shop_domain", models.CharField(blank=True, max_length=255)),
                ("last_shopify_id", models.CharField(blank=True, max_length=20)),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenancy.tenant"),
                ),
            ],
            options={
                "db_table": "shopify_sync_log",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="shopifyproduct",
            index=models.Index(fields=["tenant", "shopify_id"], name="crm_shopify_tenant__a1b2c3_idx"),
        ),
        migrations.AddIndex(
            model_name="shopifyproduct",
            index=models.Index(fields=["last_synced"], name="crm_shopify_last_sy_d4e5f6_idx"),
        ),
        migrations.AddIndex(
            model_name="shopifycustomer",
            index=models.Index(fields=["tenant", "shopify_id"], name="crm_shopify_tenant__g7h8i9_idx"),
        ),
        migrations.AddIndex(
            model_name="shopifycustomer",
            index=models.Index(fields=["email"], name="crm_shopify_email_j0k1l2_idx"),
        ),
        migrations.AddIndex(
            model_name="shopifycustomer",
            index=models.Index(fields=["last_synced"], name="crm_shopify_last_sy_m3n4o5_idx"),
        ),
        migrations.AddIndex(
            model_name="shopifyorder",
            index=models.Index(fields=["tenant", "shopify_id"], name="crm_shopify_tenant__p6q7r8_idx"),
        ),
        migrations.AddIndex(
            model_name="shopifyorder",
            index=models.Index(fields=["order_number"], name="crm_shopify_order_n_s9t0u1_idx"),
        ),
        migrations.AddIndex(
            model_name="shopifyorder",
            index=models.Index(fields=["last_synced"], name="crm_shopify_last_sy_v2w3x4_idx"),
        ),
        migrations.AddIndex(
            model_name="shopifysynclog",
            index=models.Index(fields=["tenant", "sync_type", "started_at"], name="crm_shopify_tenant__y5z6a7_idx"),
        ),
        migrations.AddIndex(
            model_name="shopifysynclog",
            index=models.Index(fields=["status"], name="crm_shopify_status_b8c9d0_idx"),
        ),
    ]
