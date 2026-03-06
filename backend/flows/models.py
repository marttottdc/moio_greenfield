import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils import timezone
from viewflow import fsm
from portal.models import Tenant

User = get_user_model()


class FlowVersionStatus(models.TextChoices):
    """Status choices for FlowVersion lifecycle."""
    DRAFT = 'draft', 'Draft'
    TESTING = 'testing', 'Testing'
    PUBLISHED = 'published', 'Published'
    ARCHIVED = 'archived', 'Archived'


# ------------------------------
#  Modelos existentes (intactos)
# ------------------------------

class Flow(models.Model):
    """Main flow definition model."""

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('error', 'Error'),
        ('archived', 'Archived'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Status - simplified (no 'testing' - that's per-version now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Published version reference - replaces is_enabled
    published_version = models.ForeignKey(
        'FlowVersion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='published_for_flows',
        help_text="Currently published version of this flow"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    # Execution stats
    execution_count = models.PositiveIntegerField(default=0)
    last_executed_at = models.DateTimeField(null=True, blank=True)
    last_execution_status = models.CharField(max_length=20, blank=True)

    class Meta:
        unique_together = ['tenant', 'name']
        indexes = [
            models.Index(fields=['tenant', 'status']),
        ]

    def __str__(self):
        return self.name

    @property
    def is_enabled(self) -> bool:
        """Flow is enabled if it has a published version and is marked active."""
        return self.published_version_id is not None and self.status == "active"

    def _cached_versions(self):
        """Cache for versions - supports both old and new models during migration."""
        versions = getattr(self, "version_list", None)
        if versions is not None:
            return versions
        # Try new FlowVersion first
        if hasattr(self, 'versions'):
            return list(self.versions.all())
        # Fall back to old FlowGraphVersion
        if hasattr(self, 'graph_versions'):
            return list(self.graph_versions.all())
        return []

    @property
    def latest_version(self):
        """Get the most recent version (any status)."""
        versions = self._cached_versions()
        return versions[0] if versions else None
    
    @property
    def testing_version(self):
        """Get the version currently in testing status, if any."""
        if hasattr(self, 'versions'):
            return self.versions.filter(status=FlowVersionStatus.TESTING).first()
        return None
    
    @property
    def draft_versions(self):
        """Get all draft versions."""
        if hasattr(self, 'versions'):
            return self.versions.filter(status=FlowVersionStatus.DRAFT)
        return self.versions.none()


class FlowExecution(models.Model):
    """Log of flow executions"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('timeout', 'Timeout'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name='executions')

    # Execution details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True, help_text="Execution duration in milliseconds")

    # Input/Output data
    input_data = models.JSONField(default=dict, help_text="Input data that triggered the flow")
    output_data = models.JSONField(default=dict, help_text="Output data from flow execution")
    error_data = models.JSONField(default=dict, help_text="Error information if execution failed")

    # Metadata
    trigger_source = models.CharField(max_length=255, blank=True, help_text="Source that triggered this execution")
    execution_context = models.JSONField(default=dict, help_text="Additional context data")

    class Meta:
        indexes = [
            models.Index(fields=['flow', '-started_at']),
            models.Index(fields=['flow', 'status']),
            models.Index(fields=['-started_at']),
        ]
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.flow.name} execution {self.id} ({self.status})"


class FlowInput(models.Model):
    """Store input data for flows (for manual triggers or scheduled flows)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name='inputs')

    name = models.CharField(max_length=255, help_text="Input parameter name")
    description = models.TextField(blank=True)
    data_type = models.CharField(max_length=50, default='string', help_text="Expected data type")
    is_required = models.BooleanField(default=False)
    default_value = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ['flow', 'name']

    def __str__(self):
        return f"{self.flow.name} - {self.name}"


class FlowSchedule(models.Model):
    """Schedule configuration for scheduled flows"""
    
    SCHEDULE_TYPE_CRON = 'cron'
    SCHEDULE_TYPE_INTERVAL = 'interval'
    SCHEDULE_TYPE_ONE_OFF = 'one_off'
    SCHEDULE_TYPE_CHOICES = [
        (SCHEDULE_TYPE_CRON, 'Cron Expression'),
        (SCHEDULE_TYPE_INTERVAL, 'Interval'),
        (SCHEDULE_TYPE_ONE_OFF, 'One-off'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flow = models.OneToOneField(Flow, on_delete=models.CASCADE, related_name='schedule')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='flow_schedules', null=True, blank=True)

    schedule_type = models.CharField(
        max_length=20,
        choices=SCHEDULE_TYPE_CHOICES,
        default=SCHEDULE_TYPE_CRON,
        help_text="Type of schedule: cron, interval, or one-off"
    )
    
    cron_expression = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Cron expression (5 fields: minute hour day month weekday)"
    )
    
    interval_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Interval in seconds for interval-based schedules"
    )
    
    run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Specific datetime for one-off schedules"
    )
    
    timezone = models.CharField(max_length=50, default='UTC')
    is_active = models.BooleanField(default=True)

    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    
    celery_task_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Name of the synced Celery Beat PeriodicTask"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['flow', 'is_active']),
        ]

    def __str__(self):
        if self.schedule_type == self.SCHEDULE_TYPE_CRON:
            return f"Schedule for {self.flow.name}: {self.cron_expression}"
        elif self.schedule_type == self.SCHEDULE_TYPE_INTERVAL:
            return f"Schedule for {self.flow.name}: every {self.interval_seconds}s"
        else:
            return f"Schedule for {self.flow.name}: at {self.run_at}"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        
        if self.schedule_type == self.SCHEDULE_TYPE_CRON and not self.cron_expression:
            raise ValidationError({'cron_expression': 'Cron expression is required for cron schedules'})
        
        if self.schedule_type == self.SCHEDULE_TYPE_INTERVAL and not self.interval_seconds:
            raise ValidationError({'interval_seconds': 'Interval seconds is required for interval schedules'})
        
        if self.schedule_type == self.SCHEDULE_TYPE_ONE_OFF and not self.run_at:
            raise ValidationError({'run_at': 'Run at datetime is required for one-off schedules'})
    
    def save(self, *args, **kwargs):
        if not self.tenant_id and self.flow_id:
            self.tenant_id = self.flow.tenant_id
        super().save(*args, **kwargs)


class FlowSignalTrigger(models.Model):
    """Registry for signal-based flow triggers.
    
    Maps Django model signals to flows, enabling automatic flow execution
    when model instances are created, updated, or deleted.
    """
    
    SIGNAL_POST_SAVE = 'post_save'
    SIGNAL_PRE_SAVE = 'pre_save'
    SIGNAL_POST_DELETE = 'post_delete'
    SIGNAL_PRE_DELETE = 'pre_delete'
    SIGNAL_M2M_CHANGED = 'm2m_changed'
    SIGNAL_TYPE_CHOICES = [
        (SIGNAL_POST_SAVE, 'After Save'),
        (SIGNAL_PRE_SAVE, 'Before Save'),
        (SIGNAL_POST_DELETE, 'After Delete'),
        (SIGNAL_PRE_DELETE, 'Before Delete'),
        (SIGNAL_M2M_CHANGED, 'Many-to-Many Changed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name='signal_triggers')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='flow_signal_triggers')
    
    model_path = models.CharField(
        max_length=255,
        help_text="Full model path, e.g., 'crm.Contact' or 'recruiter.Candidate'"
    )
    signal_type = models.CharField(
        max_length=20,
        choices=SIGNAL_TYPE_CHOICES,
        default=SIGNAL_POST_SAVE,
        help_text="Django signal type to listen for"
    )
    
    only_on_create = models.BooleanField(
        default=False,
        help_text="Only trigger when instance is created (applies to post_save/pre_save)"
    )
    only_on_update = models.BooleanField(
        default=False,
        help_text="Only trigger when instance is updated (applies to post_save/pre_save)"
    )
    
    watch_fields = models.JSONField(
        default=list,
        blank=True,
        help_text="List of field names to watch for changes. Empty means watch all fields."
    )
    
    field_conditions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Field conditions to check, e.g., {'status': 'active'}"
    )
    
    is_active = models.BooleanField(default=True)
    
    name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional friendly name for this trigger"
    )
    description = models.TextField(blank=True)
    
    execution_count = models.PositiveIntegerField(default=0)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['model_path', 'signal_type', 'is_active']),
            models.Index(fields=['flow', 'is_active']),
        ]
        verbose_name = "Flow Signal Trigger"
        verbose_name_plural = "Flow Signal Triggers"
    
    def __str__(self):
        name_part = f" ({self.name})" if self.name else ""
        return f"{self.signal_type} on {self.model_path}{name_part}"
    
    def clean(self):
        super().clean()
        if self.only_on_create and self.only_on_update:
            raise ValidationError(
                "Cannot set both only_on_create and only_on_update"
            )
        if self.signal_type in (self.SIGNAL_POST_DELETE, self.SIGNAL_PRE_DELETE):
            if self.only_on_create or self.only_on_update:
                raise ValidationError(
                    "only_on_create and only_on_update are not applicable for delete signals"
                )
            if self.watch_fields:
                raise ValidationError(
                    "watch_fields is not applicable for delete signals"
                )
    
    def save(self, *args, **kwargs):
        if not self.tenant_id and self.flow_id:
            self.tenant_id = self.flow.tenant_id
        super().save(*args, **kwargs)


class FlowWebhook(models.Model):
    """Webhook configuration for webhook-triggered flows"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flow = models.OneToOneField(Flow, on_delete=models.CASCADE, related_name='webhook')

    # Webhook details
    endpoint_path = models.CharField(max_length=255, help_text="URL path for the webhook")
    http_method = models.CharField(max_length=10, default='POST', choices=[
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('PATCH', 'PATCH'),
        ('DELETE', 'DELETE'),
    ])

    # Security
    secret_token = models.CharField(max_length=255, blank=True, help_text="Secret token for webhook verification")
    allowed_ips = models.JSONField(default=list, help_text="List of allowed IP addresses")

    # Configuration
    headers_validation = models.JSONField(default=dict, help_text="Required headers validation")
    payload_validation = models.JSONField(default=dict, help_text="Payload validation rules")

    # Stats
    total_calls = models.PositiveIntegerField(default=0)
    last_called_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['flow', 'endpoint_path']

    def __str__(self):
        return f"Webhook for {self.flow.name}: {self.http_method} {self.endpoint_path}"


# ----------------------------------------------------
#  Extensión mínima para el Flow Builder (Versionado)
# ----------------------------------------------------
class FlowGraphVersion(models.Model):
    """
    Versión del grafo (canvas) asociada a un Flow.
    
    Lifecycle States:
    - Draft (is_published=False): Editable, can be previewed when armed
    - Published (is_published=True): Locked, immutable
    - Active (is_published=True, flow.is_enabled=True): Receives live events
    - Inactive (is_published=True, flow.is_enabled=False): Historical, rollback candidate
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name="graph_versions")
    major = models.IntegerField(default=1)
    minor = models.IntegerField(default=0)
    is_published = models.BooleanField(default=False)
    graph = models.JSONField(default=dict)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    
    preview_armed = models.BooleanField(
        default=False,
        help_text="When True, this draft version temporarily receives events for preview"
    )
    preview_armed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when preview was armed"
    )
    preview_armed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='armed_flow_versions',
        help_text="User who armed this version for preview"
    )

    class Meta:
        unique_together = ("flow", "major", "minor")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["flow", "is_published"]),
            models.Index(fields=["preview_armed"]),
        ]

    def __str__(self):
        suffix = ""
        if self.is_published:
            suffix = " (published)"
        elif self.preview_armed:
            suffix = " (armed)"
        return f"{self.flow.name} v{self.major}.{self.minor}{suffix}"

    @property
    def label(self):
        if self.is_published:
            return f"v{self.major}.{self.minor} • published"
        elif self.preview_armed:
            return f"v{self.major}.{self.minor} • armed"
        return f"v{self.major}.{self.minor} • draft"
    
    @property
    def is_draft(self) -> bool:
        return not self.is_published
    
    @property
    def is_editable(self) -> bool:
        return not self.is_published
    
    def arm_for_preview(self, user=None):
        """Arm this draft version to temporarily receive events."""
        if self.is_published:
            raise ValueError("Cannot arm a published version for preview")
        self.preview_armed = True
        self.preview_armed_at = timezone.now()
        self.preview_armed_by = user
        self.save(update_fields=["preview_armed", "preview_armed_at", "preview_armed_by"])
    
    def disarm_preview(self):
        """Stop this version from receiving events."""
        self.preview_armed = False
        self.preview_armed_at = None
        self.preview_armed_by = None
        self.save(update_fields=["preview_armed", "preview_armed_at", "preview_armed_by"])


# ----------------------------------------------------
#  New FlowVersion Model (replaces FlowGraphVersion)
# ----------------------------------------------------

class FlowVersion(models.Model):
    """
    Versioned flow graph with FSM-controlled lifecycle.
    
    Lifecycle:
    - DRAFT: Editable, multiple drafts allowed per flow
    - TESTING: Supervised testing mode (only one per flow), receives events in sandbox
    - PUBLISHED: Production version (only one per flow), immutable
    - ARCHIVED: Historical versions, read-only
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name="versions")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="flow_versions")
    
    # Single version number (auto-increment per flow)
    version = models.PositiveIntegerField(default=1)
    
    # FSM-controlled status
    status = models.CharField(
        max_length=20,
        choices=FlowVersionStatus.choices,
        default=FlowVersionStatus.DRAFT,
        db_index=True
    )
    
    # Version metadata
    label = models.CharField(max_length=100, blank=True, help_text="Optional label for this version")
    notes = models.TextField(blank=True, default="")
    
    # The flow graph data
    graph = models.JSONField(default=dict)

    # Flow-scoped config variables (schema-defined, immutable at runtime).
    # These are persisted per version to ensure determinism/replay-safety.
    config_schema = models.JSONField(default=dict, blank=True)
    config_values = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # Tracks every save (for drafts)
    published_at = models.DateTimeField(null=True, blank=True)
    testing_started_at = models.DateTimeField(null=True, blank=True)
    
    # User tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_flow_versions'
    )
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["flow", "status"]),
            models.Index(fields=["flow", "-version"]),
            models.Index(fields=["tenant", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['flow', 'version'],
                name='unique_flow_version_number',
            ),
            models.UniqueConstraint(
                fields=['flow'],
                condition=Q(status='testing'),
                name='one_testing_per_flow'
            ),
            models.UniqueConstraint(
                fields=['flow'],
                condition=Q(status='published'),
                name='one_published_per_flow'
            ),
        ]
    
    def __str__(self):
        status_label = f" ({self.status})" if self.status != FlowVersionStatus.DRAFT else ""
        return f"{self.flow.name} v{self.version}{status_label}"
    
    @property
    def version_label(self) -> str:
        """Human-readable version label."""
        if self.label:
            return f"v{self.version} - {self.label}"
        return f"v{self.version} ({self.get_status_display()})"
    
    @property
    def is_editable(self) -> bool:
        """Only draft and testing versions can be edited."""
        return self.status in (FlowVersionStatus.DRAFT, FlowVersionStatus.TESTING)
    
    @property
    def is_draft(self) -> bool:
        return self.status == FlowVersionStatus.DRAFT
    
    @property
    def is_testing(self) -> bool:
        return self.status == FlowVersionStatus.TESTING
    
    @property
    def is_published(self) -> bool:
        return self.status == FlowVersionStatus.PUBLISHED
    
    @property
    def is_archived(self) -> bool:
        return self.status == FlowVersionStatus.ARCHIVED
    
    # FSM State definition
    state = fsm.State(FlowVersionStatus, default=FlowVersionStatus.DRAFT)
    
    @state.setter()
    def _set_state(self, value: FlowVersionStatus):
        self.status = value.value if isinstance(value, FlowVersionStatus) else value
    
    @state.getter()
    def _get_state(self) -> FlowVersionStatus:
        return FlowVersionStatus(self.status)
    
    @state.transition(source=FlowVersionStatus.DRAFT, target=FlowVersionStatus.TESTING)
    def start_testing(self):
        """Transition from draft to testing mode."""
        # Clear any existing testing version for this flow
        FlowVersion.objects.filter(
            flow=self.flow,
            status=FlowVersionStatus.TESTING
        ).exclude(pk=self.pk).update(
            status=FlowVersionStatus.DRAFT,
            testing_started_at=None
        )
        self.testing_started_at = timezone.now()
    
    @state.transition(source=FlowVersionStatus.TESTING, target=FlowVersionStatus.DRAFT)
    def back_to_design(self):
        """Transition from testing back to draft for more edits."""
        self.testing_started_at = None
    
    @state.transition(source=[FlowVersionStatus.DRAFT, FlowVersionStatus.TESTING], target=FlowVersionStatus.PUBLISHED)
    def publish(self):
        """Publish this version. Archives any previously published version."""
        # Archive existing published version
        FlowVersion.objects.filter(
            flow=self.flow,
            status=FlowVersionStatus.PUBLISHED
        ).exclude(pk=self.pk).update(status=FlowVersionStatus.ARCHIVED)

        # Safety: publishing should leave no other version in testing.
        FlowVersion.objects.filter(
            flow=self.flow,
            status=FlowVersionStatus.TESTING,
        ).exclude(pk=self.pk).update(
            status=FlowVersionStatus.DRAFT,
            testing_started_at=None,
        )
        
        self.published_at = timezone.now()
        self.testing_started_at = None
        
        # Update flow's published_version reference
        self.flow.published_version = self
        self.flow.save(update_fields=['published_version'])
    
    @state.transition(source=FlowVersionStatus.PUBLISHED, target=FlowVersionStatus.ARCHIVED)
    def archive(self):
        """Archive this published version."""
        # Clear flow's published_version if it points to this version
        if self.flow.published_version_id == self.pk:
            self.flow.published_version = None
            self.flow.save(update_fields=['published_version'])

    @state.transition(source=FlowVersionStatus.ARCHIVED, target=FlowVersionStatus.PUBLISHED)
    def restore(self):
        """Restore an archived version to published (reactivate)."""
        # Archive any other published version for this flow
        FlowVersion.objects.filter(
            flow=self.flow,
            status=FlowVersionStatus.PUBLISHED
        ).exclude(pk=self.pk).update(status=FlowVersionStatus.ARCHIVED)

        # Safety: restoring should leave no other version in testing.
        FlowVersion.objects.filter(
            flow=self.flow,
            status=FlowVersionStatus.TESTING,
        ).exclude(pk=self.pk).update(
            status=FlowVersionStatus.DRAFT,
            testing_started_at=None,
        )
        self.published_at = timezone.now()
        self.flow.published_version = self
        self.flow.status = 'active'
        self.flow.save(update_fields=['published_version', 'status'])

    def save(self, *args, **kwargs):
        # Block edits on published/archived versions
        if not self._state.adding and self.pk:
            old = FlowVersion.objects.filter(pk=self.pk).values('status', 'graph').first()
            if old and old['status'] in (FlowVersionStatus.PUBLISHED.value, FlowVersionStatus.ARCHIVED.value):
                # Allow status changes but not graph changes
                if self.graph != old['graph']:
                    raise ValidationError("Cannot modify graph of published or archived versions")
        
        # Auto-increment version number for new versions (race-safe).
        # NOTE: FlowVersion uses a UUID primary key with a default value, so `self.pk`
        # is already set on new instances. Use Django's state flag to detect inserts.
        if self._state.adding:
            # Set tenant from flow early for consistency.
            if not self.tenant_id and self.flow_id:
                self.tenant_id = self.flow.tenant_id

            with transaction.atomic():
                # Lock rows for this flow so concurrent creates don't assign the same version number.
                last_version = (
                    FlowVersion.objects
                    .select_for_update()
                    .filter(flow=self.flow)
                    .order_by('-version')
                    .first()
                )
                self.version = (last_version.version + 1) if last_version else 1
                return super().save(*args, **kwargs)

        return super().save(*args, **kwargs)
    
    def clone_as_draft(self, user=None) -> 'FlowVersion':
        """Create a new draft version based on this version's graph."""
        return FlowVersion.objects.create(
            flow=self.flow,
            tenant=self.tenant,
            graph=self.graph.copy() if self.graph else {},
            config_schema=(self.config_schema or {}).copy() if isinstance(getattr(self, "config_schema", None), dict) else {},
            config_values=(self.config_values or {}).copy() if isinstance(getattr(self, "config_values", None), dict) else {},
            notes=f"Cloned from v{self.version}",
            created_by=user,
        )


class FlowScript(models.Model):
    """Represents a script that can be executed within a flow."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="flow_scripts")
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name="scripts", null=True, blank=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("flow", "slug"),)
        indexes = [
            models.Index(fields=["tenant", "slug"]),
            models.Index(fields=["tenant", "flow"]),
        ]

    def __str__(self) -> str:
        if self.flow_id and self.flow:
            return f"{self.name} ({self.flow.name})"
        return self.name

    def clean(self):
        super().clean()
        if self.flow and self.flow.tenant_id != self.tenant_id:
            raise ValidationError("Flow tenant mismatch for script")

    @property
    def latest_version(self):
        return self.versions.order_by("-version_number", "-created_at").first()

    @property
    def published_version(self):
        return (
            self.versions.filter(published_at__isnull=False)
            .order_by("-published_at", "-version_number")
            .first()
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class FlowScriptVersion(models.Model):
    """Immutable snapshot of a script."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    script = models.ForeignKey(
        FlowScript, on_delete=models.CASCADE, related_name="versions"
    )
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="flow_script_versions"
    )
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name="script_versions", null=True, blank=True,)
    version_number = models.PositiveIntegerField()
    code = models.TextField()
    requirements = models.TextField(blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = (("script", "version_number"),)
        ordering = ["-version_number", "-created_at"]
        indexes = [
            models.Index(fields=["tenant", "flow"]),
            models.Index(fields=["script", "-version_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.script.name} v{self.version_number}"

    def clean(self):
        super().clean()
        if self.script.tenant_id != self.tenant_id:
            raise ValidationError("Script tenant mismatch")
        if self.script.flow_id and self.script.flow_id != self.flow_id:
            raise ValidationError("Script flow mismatch")

    @property
    def is_published(self) -> bool:
        return self.published_at is not None

    def publish(self, timestamp=None):
        """Mark this version as the published one, unpublishing any other."""

        if timestamp is None:
            timestamp = timezone.now()
        FlowScriptVersion.objects.filter(
            script=self.script, published_at__isnull=False
        ).exclude(pk=self.pk).update(published_at=None)
        self.published_at = timestamp
        self.save(update_fields=["published_at"])

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class FlowScriptRun(models.Model):
    """Execution record for a script version."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="flow_script_runs"
    )
    flow = models.ForeignKey(
        Flow,
        on_delete=models.CASCADE,
        related_name="script_runs",
        null=True,
        blank=True,
    )
    script = models.ForeignKey(
        FlowScript, on_delete=models.CASCADE, related_name="runs"
    )
    version = models.ForeignKey(
        FlowScriptVersion, on_delete=models.CASCADE, related_name="runs"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    input_payload = models.JSONField(default=dict, blank=True)
    output_payload = models.JSONField(default=dict, blank=True)
    error_payload = models.JSONField(default=dict, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True, default='')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "flow"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["script", "-started_at"]),
        ]

    def __str__(self) -> str:
        return f"Run {self.id} for {self.script.name} v{self.version.version_number}"

    def clean(self):
        super().clean()
        if self.script_id != self.version.script_id:
            raise ValidationError("Version does not belong to the script")
        if not self.flow_id and self.script.flow_id:
            self.flow = self.script.flow
        if self.script.flow_id and self.flow_id != self.script.flow_id:
            raise ValidationError("Run flow mismatch")
        if self.tenant_id != self.script.tenant_id:
            raise ValidationError("Run tenant mismatch")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def duration_ms(self) -> int | None:
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None

    @property
    def is_finished(self) -> bool:
        return self.status in {self.STATUS_FAILED, self.STATUS_SUCCESS}


class FlowScriptLog(models.Model):
    """Log entry captured during a script run."""

    LEVEL_INFO = "info"
    LEVEL_WARNING = "warning"
    LEVEL_ERROR = "error"
    LEVEL_CHOICES = [
        (LEVEL_INFO, "Info"),
        (LEVEL_WARNING, "Warning"),
        (LEVEL_ERROR, "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        FlowScriptRun, on_delete=models.CASCADE, related_name="logs"
    )
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="flow_script_logs"
    )
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default=LEVEL_INFO)
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "level"]),
            models.Index(fields=["run", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.level}] {self.message[:50]}"

    def clean(self):
        super().clean()
        if self.tenant_id != self.run.tenant_id:
            raise ValidationError("Log tenant mismatch")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class EventDefinition(models.Model):
    """
    Registry of available events that can trigger flows.
    
    Events follow the naming convention: <entity>.<action>
    Examples: deal.won, message.sent, contact.created
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    name = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="Event name in format: entity.action (e.g., deal.won, contact.created)"
    )
    label = models.CharField(
        max_length=255,
        help_text="Human-readable label for the event"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of when this event is emitted"
    )
    
    entity_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Primary entity type (e.g., deal, contact, ticket)"
    )
    
    payload_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON Schema defining the expected payload structure"
    )
    
    hints = models.JSONField(
        default=dict,
        blank=True,
        help_text="Usage hints including example payloads, use cases, and configuration tips"
    )
    
    active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this event can be used in new flow triggers"
    )
    
    category = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Category for grouping events (e.g., crm, chatbot, recruiter)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "flows_event_definition"
        ordering = ["category", "name"]
        indexes = [
            models.Index(fields=["entity_type", "active"]),
            models.Index(fields=["category", "active"]),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.label})"
    
    @classmethod
    def get_or_create_event(
        cls,
        name: str,
        label: str,
        entity_type: str,
        description: str = "",
        category: str = "",
        payload_schema: dict = None,
    ):
        """Get or create an event definition."""
        event, created = cls.objects.get_or_create(
            name=name,
            defaults={
                "label": label,
                "entity_type": entity_type,
                "description": description,
                "category": category,
                "payload_schema": payload_schema or {},
            }
        )
        return event, created


class EventLog(models.Model):
    """
    Immutable log of emitted events.
    
    Every event emission is persisted here for:
    - Audit trail
    - Debugging
    - Replay capabilities
    - Deterministic flow execution
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    name = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Event name (e.g., deal.won)"
    )
    
    tenant_id = models.UUIDField(
        db_index=True,
        help_text="Tenant that owns this event"
    )
    
    actor = models.JSONField(
        null=True,
        blank=True,
        help_text="Initiator of the event: {type: 'user'|'system'|'service', id: 'uuid'}"
    )
    
    entity = models.JSONField(
        null=True,
        blank=True,
        help_text="Primary entity affected: {type: 'deal'|'contact'|..., id: 'uuid'}"
    )
    
    payload = models.JSONField(
        default=dict,
        help_text="Arbitrary structured event data"
    )
    
    occurred_at = models.DateTimeField(
        db_index=True,
        help_text="When the event occurred (business time)"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the event was persisted (system time)"
    )
    
    correlation_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="ID to correlate related events"
    )
    
    source = models.CharField(
        max_length=255,
        blank=True,
        help_text="Source that emitted the event (e.g., api, task, webhook)"
    )
    
    routed = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this event has been routed to matching flows"
    )
    
    routed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the event was routed"
    )
    
    flow_executions = models.JSONField(
        default=list,
        blank=True,
        help_text="List of flow execution IDs triggered by this event"
    )
    
    class Meta:
        db_table = "flows_event_log"
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["tenant_id", "-occurred_at"]),
            models.Index(fields=["name", "tenant_id", "-occurred_at"]),
            models.Index(fields=["routed", "-occurred_at"]),
        ]
    
    def __str__(self):
        return f"{self.name} @ {self.occurred_at.isoformat()}"
    
    def mark_routed(self, flow_execution_ids: list = None):
        """Mark this event as routed to flows."""
        self.routed = True
        self.routed_at = timezone.now()
        if flow_execution_ids:
            self.flow_executions = flow_execution_ids
        self.save(update_fields=["routed", "routed_at", "flow_executions"])


class ScheduledTask(models.Model):
    """
    General-purpose scheduled Celery task management.
    Tenant-scoped model for scheduling any Celery task with custom parameters.
    """
    
    SCHEDULE_TYPE_CRON = 'cron'
    SCHEDULE_TYPE_INTERVAL = 'interval'
    SCHEDULE_TYPE_ONE_OFF = 'one_off'
    SCHEDULE_TYPE_CHOICES = [
        (SCHEDULE_TYPE_CRON, 'Cron Expression'),
        (SCHEDULE_TYPE_INTERVAL, 'Interval'),
        (SCHEDULE_TYPE_ONE_OFF, 'One-off'),
    ]
    
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='scheduled_tasks')
    
    name = models.CharField(max_length=255, help_text="Human-readable name for this scheduled task")
    description = models.TextField(blank=True, help_text="Description of what this task does")
    
    task_name = models.CharField(
        max_length=255,
        help_text="Full Celery task name (e.g., 'crm.tasks.sync_contacts')"
    )
    task_args = models.JSONField(
        default=list,
        blank=True,
        help_text="Positional arguments to pass to the task"
    )
    task_kwargs = models.JSONField(
        default=dict,
        blank=True,
        help_text="Keyword arguments to pass to the task"
    )
    
    schedule_type = models.CharField(
        max_length=20,
        choices=SCHEDULE_TYPE_CHOICES,
        default=SCHEDULE_TYPE_CRON,
    )
    cron_expression = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Cron expression (5 fields: minute hour day month weekday)"
    )
    interval_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Interval in seconds for interval-based schedules"
    )
    run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Specific datetime for one-off schedules"
    )
    timezone = models.CharField(max_length=50, default='UTC')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    is_active = models.BooleanField(default=True)
    
    celery_task_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Name of the synced Celery Beat PeriodicTask"
    )
    
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    run_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = "flows_scheduled_task"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["task_name"]),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.task_name})"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        
        if self.schedule_type == self.SCHEDULE_TYPE_CRON and not self.cron_expression:
            raise ValidationError({'cron_expression': 'Cron expression is required for cron schedules'})
        
        if self.schedule_type == self.SCHEDULE_TYPE_INTERVAL and not self.interval_seconds:
            raise ValidationError({'interval_seconds': 'Interval seconds is required for interval schedules'})
        
        if self.schedule_type == self.SCHEDULE_TYPE_ONE_OFF and not self.run_at:
            raise ValidationError({'run_at': 'Run at datetime is required for one-off schedules'})


class TaskExecution(models.Model):
    """
    Execution history for scheduled tasks.
    Tracks each run of a scheduled task with status, timing, and results.
    """
    
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_TIMEOUT = 'timeout'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_TIMEOUT, 'Timeout'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scheduled_task = models.ForeignKey(
        ScheduledTask,
        on_delete=models.CASCADE,
        related_name='executions'
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='task_executions')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    
    celery_task_id = models.CharField(max_length=255, blank=True, default='')
    
    input_data = models.JSONField(default=dict, blank=True, help_text="Args/kwargs passed to the task")
    result_data = models.JSONField(default=dict, blank=True, help_text="Task return value")
    error_message = models.TextField(blank=True, default='')
    error_traceback = models.TextField(blank=True, default='')
    
    trigger_type = models.CharField(
        max_length=50,
        default='scheduled',
        help_text="How the execution was triggered: scheduled, manual, api"
    )
    
    class Meta:
        db_table = "flows_task_execution"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["scheduled_task", "-started_at"]),
            models.Index(fields=["tenant", "-started_at"]),
            models.Index(fields=["status"]),
        ]
    
    def __str__(self):
        return f"{self.scheduled_task.name} execution @ {self.started_at}"
    
    def mark_running(self):
        self.status = self.STATUS_RUNNING
        self.save(update_fields=["status"])
    
    def mark_success(self, result=None):
        self.status = self.STATUS_SUCCESS
        self.finished_at = timezone.now()
        if self.started_at:
            self.duration_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)
        if result:
            self.result_data = result if isinstance(result, dict) else {"result": str(result)}
        self.save(update_fields=["status", "finished_at", "duration_ms", "result_data"])
        
        self.scheduled_task.run_count += 1
        self.scheduled_task.last_run_at = self.finished_at
        self.scheduled_task.save(update_fields=["run_count", "last_run_at"])
    
    def mark_failed(self, error_message: str, traceback: str = ''):
        self.status = self.STATUS_FAILED
        self.finished_at = timezone.now()
        if self.started_at:
            self.duration_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)
        self.error_message = error_message
        self.error_traceback = traceback
        self.save(update_fields=["status", "finished_at", "duration_ms", "error_message", "error_traceback"])
        
        self.scheduled_task.error_count += 1
        self.scheduled_task.last_run_at = self.finished_at
        self.scheduled_task.save(update_fields=["error_count", "last_run_at"])


class FlowAgentContext(models.Model):
    """
    Shared agentic context for an entire flow execution.
    Multiple agents can read/write to this shared context during a flow run.
    """
    
    STATUS_ACTIVE = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='flow_agent_contexts')
    flow_execution = models.OneToOneField(
        FlowExecution,
        on_delete=models.CASCADE,
        related_name='agent_context',
        help_text="The flow execution this context belongs to"
    )
    
    shared_variables = models.JSONField(
        default=dict,
        blank=True,
        help_text="Accumulated context variables all agents can read/write"
    )
    conversation_history = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered list of all conversation turns across agents"
    )
    tool_calls_log = models.JSONField(
        default=list,
        blank=True,
        help_text="Append-only log of all tool calls for traceability"
    )
    reasoning_trace = models.TextField(
        blank=True,
        default='',
        help_text="Optional aggregated reasoning/debug information"
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arbitrary orchestration flags and metadata"
    )
    
    class Meta:
        db_table = "flows_agent_context"
        indexes = [
            models.Index(fields=['tenant', '-started_at']),
            models.Index(fields=['flow_execution']),
        ]
    
    def __str__(self):
        return f"AgentContext for execution {self.flow_execution_id}"
    
    def append_conversation(self, role: str, content: str, agent_name: str = None):
        """Append a message to the conversation history (copy to avoid concurrency issues)."""
        entry = {
            'role': role,
            'content': content,
            'timestamp': timezone.now().isoformat(),
        }
        if agent_name:
            entry['agent'] = agent_name
        # Copy list to avoid in-place mutation issues with concurrent access
        new_history = list(self.conversation_history or [])
        new_history.append(entry)
        self.conversation_history = new_history
    
    def append_tool_call(self, tool_name: str, args: dict, result: any, latency_ms: int = None, agent_name: str = None):
        """Log a tool call (copy to avoid concurrency issues)."""
        entry = {
            'tool': tool_name,
            'args': args,
            'result': result,
            'timestamp': timezone.now().isoformat(),
        }
        if latency_ms is not None:
            entry['latency_ms'] = latency_ms
        if agent_name:
            entry['agent'] = agent_name
        # Copy list to avoid in-place mutation issues with concurrent access
        new_log = list(self.tool_calls_log or [])
        new_log.append(entry)
        self.tool_calls_log = new_log
    
    def merge_variables(self, new_vars: dict):
        """Merge new variables into shared context (copy to avoid mutation issues)."""
        new_shared = dict(self.shared_variables or {})
        new_shared.update(new_vars)
        self.shared_variables = new_shared
    
    def mark_completed(self):
        """Mark context as completed."""
        self.status = self.STATUS_COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])
    
    def mark_failed(self):
        """Mark context as failed."""
        self.status = self.STATUS_FAILED
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])


class FlowAgentTurn(models.Model):
    """
    Individual agent contribution within a flow execution.
    Provides fine-grained audit trail for each agent invocation.
    """
    
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    context = models.ForeignKey(
        FlowAgentContext,
        on_delete=models.CASCADE,
        related_name='turns',
        help_text="The parent agent context"
    )
    run_index = models.PositiveIntegerField(
        default=0,
        help_text="Order of this turn within the context (0-indexed)"
    )
    
    agent_name = models.CharField(
        max_length=255,
        help_text="Name of the agent that executed this turn"
    )
    node_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Flow node that triggered this agent"
    )
    
    input_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Input provided to the agent"
    )
    output_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Output produced by the agent"
    )
    
    tool_calls = models.JSONField(
        default=list,
        blank=True,
        help_text="Tool calls made during this turn"
    )
    messages = models.JSONField(
        default=list,
        blank=True,
        help_text="Conversation messages in this turn"
    )
    errors = models.JSONField(
        default=list,
        blank=True,
        help_text="Any errors that occurred"
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    
    class Meta:
        db_table = "flows_agent_turn"
        ordering = ['run_index']
        indexes = [
            models.Index(fields=['context', 'run_index']),
            models.Index(fields=['agent_name']),
        ]
        unique_together = ['context', 'run_index']
    
    def __str__(self):
        return f"Turn {self.run_index}: {self.agent_name}"
    
    def mark_completed(self, output: dict = None):
        """Mark turn as completed with output."""
        self.status = self.STATUS_COMPLETED
        self.completed_at = timezone.now()
        if self.started_at:
            self.duration_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
        if output:
            self.output_payload = output
        self.save(update_fields=['status', 'completed_at', 'duration_ms', 'output_payload'])
    
    def mark_failed(self, error: str):
        """Mark turn as failed."""
        self.status = self.STATUS_FAILED
        self.completed_at = timezone.now()
        if self.started_at:
            self.duration_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
        self.errors.append({'error': error, 'timestamp': timezone.now().isoformat()})
        self.save(update_fields=['status', 'completed_at', 'duration_ms', 'errors'])
