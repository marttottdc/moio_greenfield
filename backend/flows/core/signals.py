"""
Flow-related signal handlers.

Contains signal handlers for:
- Flow schedule syncing to Celery Beat
- Flow webhook cleanup on deletion
"""

from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)

EXCLUDED_MODELS = {
    "flows.Flow",
    "flows.FlowExecution",
    "flows.FlowGraphVersion",
    "flows.FlowVersion",
    "flows.FlowSchedule",
    "flows.FlowSignalTrigger",
    "flows.FlowWebhook",
    "flows.FlowInput",
    "flows.FlowScript",
    "flows.FlowScriptVersion",
    "flows.FlowScriptRun",
    "flows.FlowScriptLog",
    "flows.EventDefinition",
    "flows.EventLog",
    "django_celery_beat.PeriodicTask",
    "django_celery_beat.CrontabSchedule",
    "django_celery_beat.IntervalSchedule",
    "django_celery_beat.ClockedSchedule",
    "auth.User",
    "sessions.Session",
    "contenttypes.ContentType",
    "admin.LogEntry",
}


def _is_excluded_model(sender) -> bool:
    """Check if model should be excluded from signal processing."""
    if not hasattr(sender, "_meta"):
        return True
    model_label = sender._meta.label
    return model_label in EXCLUDED_MODELS


def _cleanup_webhook_flow_links(flow_instance):
    """Remove flow from all linked webhooks when flow is deleted."""
    try:
        from crm.models import WebhookConfig
    except ImportError:
        return
    
    webhooks = WebhookConfig.objects.filter(linked_flows=flow_instance)
    for webhook in webhooks:
        webhook.linked_flows.remove(flow_instance)
        logger.debug(f"Removed flow {flow_instance.id} from webhook {webhook.id}")


@receiver(pre_delete)
def handle_pre_delete_flows(sender, instance, **kwargs):
    """Handle pre_delete signals for flow cleanup."""
    if _is_excluded_model(sender):
        return

    from flows.models import Flow
    
    if sender == Flow:
        _cleanup_webhook_flow_links(instance)


@receiver(post_save)
def sync_flow_schedule_on_save(sender, instance, created, **kwargs):
    """Sync FlowSchedule to Celery Beat on save."""
    from flows.models import FlowSchedule
    
    if sender != FlowSchedule:
        return
    
    update_fields = kwargs.get('update_fields')
    if update_fields is not None:
        if set(update_fields) <= {'celery_task_name', 'last_run_at', 'next_run_at'}:
            return
    
    try:
        from flows.core.schedule_service import ScheduleService
        ScheduleService.sync_schedule(instance)
        logger.info(f"Synced FlowSchedule {instance.id} to Celery Beat")
    except Exception as e:
        logger.error(f"Failed to sync FlowSchedule {instance.id}: {e}")


@receiver(post_delete)
def delete_flow_schedule_on_delete(sender, instance, **kwargs):
    """Delete Celery Beat task when FlowSchedule is deleted."""
    from flows.models import FlowSchedule
    
    if sender != FlowSchedule:
        return
    
    try:
        from flows.core.schedule_service import ScheduleService
        ScheduleService.delete_schedule(instance)
        logger.info(f"Deleted Celery Beat task for FlowSchedule {instance.id}")
    except Exception as e:
        logger.error(f"Failed to delete Celery Beat task for FlowSchedule {instance.id}: {e}")


@receiver(post_save)
def sync_schedule_from_flow_version(sender, instance, created, **kwargs):
    """
    Auto-create/update FlowSchedule from trigger_scheduled node in FlowVersion graph.
    
    - On first save (create): Creates inactive FlowSchedule if trigger_scheduled exists
    - On status change to testing/published: Activates the schedule
    - On status change to draft/archived: Deactivates the schedule
    - On graph update: Updates schedule config or deletes if trigger removed
    
    Always syncs graph first (to ensure config is up-to-date), then handles 
    status-based activation.
    """
    from flows.models import FlowVersion
    
    if sender != FlowVersion:
        return
    
    update_fields = kwargs.get('update_fields')
    if update_fields is not None:
        skip_fields = {'updated_at', 'published_at', 'testing_started_at'}
        if set(update_fields) <= skip_fields:
            return
    
    try:
        from flows.core.schedule_service import ScheduleService
        from flows.models import FlowSchedule, FlowVersionStatus, FlowVersion
        
        flow = instance.flow
        # Determine the active version that should drive scheduling.
        # Priority: published > testing. Draft/archived versions never delete schedules.
        driver = (
            FlowVersion.objects.filter(flow=flow, status=FlowVersionStatus.PUBLISHED).first()
            or FlowVersion.objects.filter(flow=flow, status=FlowVersionStatus.TESTING).first()
        )
        
        if driver:
            graph = driver.graph or {}
            schedule = ScheduleService.sync_schedule_from_graph(driver, graph, allow_delete=True)
            if schedule:
                ScheduleService.update_schedule_activation(driver)
                logger.info(f"Synced schedule from active FlowVersion {driver.id} status={driver.status}")
            else:
                # If the active version has no trigger_scheduled, allow_delete=True will delete the schedule.
                logger.info(f"No schedule configured from active FlowVersion {driver.id} status={driver.status}")
        else:
            # No active version: ensure schedule does not run, but do not delete it.
            try:
                schedule = FlowSchedule.objects.get(flow=flow)
            except FlowSchedule.DoesNotExist:
                schedule = None
            if schedule and schedule.is_active:
                ScheduleService.deactivate_schedule(schedule)
                logger.info(f"Deactivated FlowSchedule {schedule.id} (no active version for flow {flow.id})")
    except Exception as e:
        logger.error(f"Failed to sync schedule for FlowVersion {instance.id}: {e}")
