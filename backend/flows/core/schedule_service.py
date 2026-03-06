"""
Schedule Service - Syncs FlowSchedule to Celery Beat

This service handles the synchronization between FlowSchedule records
and Django Celery Beat's PeriodicTask entries, enabling dynamic
scheduling without requiring Celery Beat restarts.
"""

from __future__ import annotations

import json
import logging
from typing import Optional, TYPE_CHECKING

from django.db import transaction
from django_celery_beat.models import (
    PeriodicTask,
    CrontabSchedule,
    IntervalSchedule,
    ClockedSchedule,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from flows.models import FlowSchedule


class ScheduleService:
    """Service for managing FlowSchedule <-> Celery Beat synchronization."""
    
    TASK_NAME_PREFIX = "flow_schedule_"
    TASK_PATH = "flows.tasks.execute_scheduled_flow"
    
    @classmethod
    def get_task_name(cls, schedule_id: str) -> str:
        """Generate a unique task name for a FlowSchedule."""
        return f"{cls.TASK_NAME_PREFIX}{schedule_id}"
    
    @classmethod
    def sync_schedule(cls, flow_schedule) -> Optional[PeriodicTask]:
        """
        Sync a FlowSchedule to Celery Beat.
        Creates or updates the corresponding PeriodicTask.
        
        Args:
            flow_schedule: FlowSchedule instance
            
        Returns:
            The created/updated PeriodicTask, or None if schedule is inactive
        """
        from flows.models import FlowSchedule
        
        task_name = cls.get_task_name(str(flow_schedule.id))
        
        if not flow_schedule.is_active:
            cls.delete_periodic_task(task_name)
            flow_schedule.celery_task_name = ''
            flow_schedule.save(update_fields=['celery_task_name'])
            return None
        
        task_kwargs = json.dumps({
            'schedule_id': str(flow_schedule.id),
            'flow_id': str(flow_schedule.flow_id),
            'tenant_id': str(flow_schedule.tenant_id),
        })
        
        with transaction.atomic():
            if flow_schedule.schedule_type == FlowSchedule.SCHEDULE_TYPE_CRON:
                periodic_task = cls._sync_cron_schedule(flow_schedule, task_name, task_kwargs)
            elif flow_schedule.schedule_type == FlowSchedule.SCHEDULE_TYPE_INTERVAL:
                periodic_task = cls._sync_interval_schedule(flow_schedule, task_name, task_kwargs)
            elif flow_schedule.schedule_type == FlowSchedule.SCHEDULE_TYPE_ONE_OFF:
                periodic_task = cls._sync_one_off_schedule(flow_schedule, task_name, task_kwargs)
            else:
                logger.warning(f"Unknown schedule type: {flow_schedule.schedule_type}")
                return None
            
            flow_schedule.celery_task_name = task_name
            flow_schedule.save(update_fields=['celery_task_name'])
            
        logger.info(f"Synced FlowSchedule {flow_schedule.id} to PeriodicTask {task_name}")
        return periodic_task
    
    @classmethod
    def _sync_cron_schedule(cls, flow_schedule, task_name: str, task_kwargs: str) -> PeriodicTask:
        """Sync a cron-based schedule."""
        cron_parts = flow_schedule.cron_expression.split()
        if len(cron_parts) != 5:
            raise ValueError(f"Invalid cron expression: {flow_schedule.cron_expression}")
        
        minute, hour, day_of_month, month, day_of_week = cron_parts
        
        crontab, _ = CrontabSchedule.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month,
            day_of_week=day_of_week,
            timezone=flow_schedule.timezone,
        )
        
        periodic_task, created = PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                'task': cls.TASK_PATH,
                'crontab': crontab,
                'interval': None,
                'clocked': None,
                'kwargs': task_kwargs,
                'enabled': True,
                'one_off': False,
                'description': f"Flow schedule for {flow_schedule.flow.name}",
            }
        )
        return periodic_task
    
    @classmethod
    def _sync_interval_schedule(cls, flow_schedule, task_name: str, task_kwargs: str) -> PeriodicTask:
        """Sync an interval-based schedule."""
        interval, _ = IntervalSchedule.objects.get_or_create(
            every=flow_schedule.interval_seconds,
            period=IntervalSchedule.SECONDS,
        )
        
        periodic_task, created = PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                'task': cls.TASK_PATH,
                'interval': interval,
                'crontab': None,
                'clocked': None,
                'kwargs': task_kwargs,
                'enabled': True,
                'one_off': False,
                'description': f"Flow schedule for {flow_schedule.flow.name}",
            }
        )
        return periodic_task
    
    @classmethod
    def _sync_one_off_schedule(cls, flow_schedule, task_name: str, task_kwargs: str) -> PeriodicTask:
        """Sync a one-off schedule."""
        clocked, _ = ClockedSchedule.objects.get_or_create(
            clocked_time=flow_schedule.run_at,
        )
        
        periodic_task, created = PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                'task': cls.TASK_PATH,
                'clocked': clocked,
                'interval': None,
                'crontab': None,
                'kwargs': task_kwargs,
                'enabled': True,
                'one_off': True,
                'description': f"Flow schedule for {flow_schedule.flow.name}",
            }
        )
        return periodic_task
    
    @classmethod
    def delete_periodic_task(cls, task_name: str) -> bool:
        """
        Delete a PeriodicTask by name.
        
        Args:
            task_name: Name of the task to delete
            
        Returns:
            True if deleted, False if not found
        """
        deleted_count, _ = PeriodicTask.objects.filter(name=task_name).delete()
        if deleted_count:
            logger.info(f"Deleted PeriodicTask: {task_name}")
            return True
        return False
    
    @classmethod
    def delete_schedule(cls, flow_schedule) -> bool:
        """
        Delete the Celery Beat task for a FlowSchedule.
        
        Args:
            flow_schedule: FlowSchedule instance
            
        Returns:
            True if deleted, False if not found
        """
        task_name = cls.get_task_name(str(flow_schedule.id))
        return cls.delete_periodic_task(task_name)
    
    @classmethod
    def activate_schedule(cls, flow_schedule) -> Optional[PeriodicTask]:
        """
        Activate a schedule (set is_active=True and sync).
        
        Args:
            flow_schedule: FlowSchedule instance
            
        Returns:
            The created/updated PeriodicTask
        """
        flow_schedule.is_active = True
        flow_schedule.save(update_fields=['is_active'])
        return cls.sync_schedule(flow_schedule)
    
    @classmethod
    def deactivate_schedule(cls, flow_schedule) -> None:
        """
        Deactivate a schedule (set is_active=False and remove Celery task).
        
        Args:
            flow_schedule: FlowSchedule instance
        """
        cls.delete_schedule(flow_schedule)
        flow_schedule.is_active = False
        flow_schedule.celery_task_name = ''
        flow_schedule.save(update_fields=['is_active', 'celery_task_name'])
    
    @classmethod
    def toggle_schedule(cls, flow_schedule) -> bool:
        """
        Toggle a schedule's active state.
        
        Args:
            flow_schedule: FlowSchedule instance
            
        Returns:
            The new is_active state
        """
        if flow_schedule.is_active:
            cls.deactivate_schedule(flow_schedule)
            return False
        else:
            cls.activate_schedule(flow_schedule)
            return True
    
    @classmethod
    def sync_schedule_from_graph(
        cls,
        version,
        graph: dict,
        *,
        allow_delete: bool = False,
    ) -> Optional["FlowSchedule"]:
        """
        Auto-create/update/delete FlowSchedule from trigger_scheduled node config.
        
        Called when a FlowVersion is saved. Always creates an inactive FlowSchedule.
        Activation is handled separately by update_schedule_activation() when 
        version status changes to 'testing' or 'published'.
        
        Args:
            version: FlowVersion instance
            graph: Flow graph dict containing nodes
            
        Returns:
            FlowSchedule instance if created/updated, None if no trigger_scheduled node
        """
        from flows.models import FlowSchedule
        
        nodes = graph.get("nodes", [])
        trigger_node = None
        
        for node in nodes:
            if node.get("kind") == "trigger_scheduled" or node.get("type") == "trigger_scheduled":
                trigger_node = node
                break
        
        flow = version.flow
        
        if not trigger_node:
            # Do not delete schedules as a side-effect of saving non-active versions (draft clones/edits).
            # Deletion is only allowed when explicitly requested by the caller (typically when the
            # active version no longer contains a trigger_scheduled node).
            if not allow_delete:
                return None
            try:
                existing_schedule = FlowSchedule.objects.get(flow=flow)
                cls.delete_schedule(existing_schedule)
                existing_schedule.celery_task_name = ''
                existing_schedule.save(update_fields=['celery_task_name'])
                existing_schedule.delete()
                logger.info(f"Deleted FlowSchedule for flow {flow.id} - trigger_scheduled node removed")
            except FlowSchedule.DoesNotExist:
                pass
            return None
        
        config = trigger_node.get("config") or trigger_node.get("data", {}).get("config", {})
        
        schedule_type = config.get("schedule_type", FlowSchedule.SCHEDULE_TYPE_CRON)
        cron_expression = config.get("cron_expression", "0 9 * * *")
        interval_seconds = config.get("interval_seconds")
        run_at = config.get("run_at")
        timezone_str = config.get("timezone", "UTC")
        
        schedule, created = FlowSchedule.objects.update_or_create(
            flow=flow,
            defaults={
                "tenant": flow.tenant,
                "schedule_type": schedule_type,
                "cron_expression": cron_expression if schedule_type == FlowSchedule.SCHEDULE_TYPE_CRON else "",
                "interval_seconds": interval_seconds if schedule_type == FlowSchedule.SCHEDULE_TYPE_INTERVAL else None,
                "run_at": run_at if schedule_type == FlowSchedule.SCHEDULE_TYPE_ONE_OFF else None,
                "timezone": timezone_str,
            }
        )
        
        logger.info(f"{'Created' if created else 'Updated'} FlowSchedule {schedule.id} for flow {flow.id}")
        
        return schedule
    
    @classmethod
    def update_schedule_activation(cls, version) -> None:
        """
        Update FlowSchedule activation based on version status.
        
        Activates schedule when version is 'testing' or 'published'.
        Deactivates when status is 'draft' or 'archived'.
        
        Args:
            version: FlowVersion instance
        """
        from flows.models import FlowSchedule, FlowVersionStatus
        
        try:
            schedule = FlowSchedule.objects.get(flow=version.flow)
        except FlowSchedule.DoesNotExist:
            return
        
        should_be_active = version.status in (
            FlowVersionStatus.TESTING,
            FlowVersionStatus.PUBLISHED,
        )
        
        if should_be_active:
            schedule.is_active = True
            schedule.save(update_fields=['is_active'])
            cls.sync_schedule(schedule)
            logger.info(f"Synced FlowSchedule {schedule.id} for version status {version.status}")
        elif schedule.is_active:
            cls.deactivate_schedule(schedule)
            logger.info(f"Deactivated FlowSchedule {schedule.id} for version status {version.status}")
