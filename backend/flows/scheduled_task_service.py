"""
Scheduled Task Service

Handles synchronization between ScheduledTask model and Celery Beat.
Provides methods for creating, updating, deleting, and executing scheduled tasks.
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Any

from celery import current_app
from django.db import transaction
from django_celery_beat.models import PeriodicTask, CrontabSchedule, IntervalSchedule

logger = logging.getLogger(__name__)


class ScheduledTaskService:
    """Service for managing scheduled tasks and Celery Beat synchronization."""
    
    TASK_NAME_PREFIX = "scheduled_task_"
    EXECUTOR_TASK = "flows.tasks.execute_scheduled_task"
    
    @classmethod
    def get_task_name(cls, task_id: str) -> str:
        """Generate a unique task name for Celery Beat."""
        return f"{cls.TASK_NAME_PREFIX}{task_id}"
    
    @classmethod
    def sync_task(cls, scheduled_task) -> Optional[PeriodicTask]:
        """
        Sync a ScheduledTask to Celery Beat.
        Creates or updates the corresponding PeriodicTask.
        """
        from flows.models import ScheduledTask
        
        task_name = cls.get_task_name(str(scheduled_task.id))
        
        if not scheduled_task.is_active:
            cls.delete_periodic_task(task_name)
            scheduled_task.celery_task_name = ''
            scheduled_task.save(update_fields=['celery_task_name'])
            return None
        
        task_kwargs = json.dumps({
            'scheduled_task_id': str(scheduled_task.id),
            'tenant_id': str(scheduled_task.tenant_id),
        })
        
        with transaction.atomic():
            if scheduled_task.schedule_type == ScheduledTask.SCHEDULE_TYPE_CRON:
                periodic_task = cls._sync_cron_schedule(scheduled_task, task_name, task_kwargs)
            elif scheduled_task.schedule_type == ScheduledTask.SCHEDULE_TYPE_INTERVAL:
                periodic_task = cls._sync_interval_schedule(scheduled_task, task_name, task_kwargs)
            elif scheduled_task.schedule_type == ScheduledTask.SCHEDULE_TYPE_ONE_OFF:
                periodic_task = cls._sync_one_off_schedule(scheduled_task, task_name, task_kwargs)
            else:
                logger.warning(f"Unknown schedule type: {scheduled_task.schedule_type}")
                return None
            
            scheduled_task.celery_task_name = task_name
            scheduled_task.save(update_fields=['celery_task_name'])
        
        logger.info(f"Synced ScheduledTask {scheduled_task.id} to PeriodicTask {task_name}")
        return periodic_task
    
    @classmethod
    def _sync_cron_schedule(cls, scheduled_task, task_name: str, task_kwargs: str) -> PeriodicTask:
        """Sync a cron-based schedule."""
        cron_parts = scheduled_task.cron_expression.split()
        if len(cron_parts) != 5:
            raise ValueError(f"Invalid cron expression: {scheduled_task.cron_expression}")
        
        minute, hour, day_of_month, month_of_year, day_of_week = cron_parts
        
        crontab, _ = CrontabSchedule.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
            timezone=scheduled_task.timezone,
        )
        
        periodic_task, created = PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                'task': cls.EXECUTOR_TASK,
                'crontab': crontab,
                'interval': None,
                'clocked': None,
                'kwargs': task_kwargs,
                'enabled': scheduled_task.is_active,
                'description': scheduled_task.description or f"Scheduled task: {scheduled_task.name}",
            }
        )
        
        return periodic_task
    
    @classmethod
    def _sync_interval_schedule(cls, scheduled_task, task_name: str, task_kwargs: str) -> PeriodicTask:
        """Sync an interval-based schedule."""
        interval, _ = IntervalSchedule.objects.get_or_create(
            every=scheduled_task.interval_seconds,
            period=IntervalSchedule.SECONDS,
        )
        
        periodic_task, created = PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                'task': cls.EXECUTOR_TASK,
                'interval': interval,
                'crontab': None,
                'clocked': None,
                'kwargs': task_kwargs,
                'enabled': scheduled_task.is_active,
                'description': scheduled_task.description or f"Scheduled task: {scheduled_task.name}",
            }
        )
        
        return periodic_task
    
    @classmethod
    def _sync_one_off_schedule(cls, scheduled_task, task_name: str, task_kwargs: str) -> PeriodicTask:
        """Sync a one-off schedule."""
        from django_celery_beat.models import ClockedSchedule
        
        clocked, _ = ClockedSchedule.objects.get_or_create(
            clocked_time=scheduled_task.run_at,
        )
        
        periodic_task, created = PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                'task': cls.EXECUTOR_TASK,
                'clocked': clocked,
                'crontab': None,
                'interval': None,
                'kwargs': task_kwargs,
                'enabled': scheduled_task.is_active,
                'one_off': True,
                'description': scheduled_task.description or f"Scheduled task: {scheduled_task.name}",
            }
        )
        
        return periodic_task
    
    @classmethod
    def delete_periodic_task(cls, task_name: str) -> bool:
        """Delete a PeriodicTask by name."""
        deleted_count, _ = PeriodicTask.objects.filter(name=task_name).delete()
        if deleted_count:
            logger.info(f"Deleted PeriodicTask: {task_name}")
            return True
        return False
    
    @classmethod
    def delete_task(cls, scheduled_task) -> None:
        """Delete the Celery Beat task for a ScheduledTask."""
        if scheduled_task.celery_task_name:
            cls.delete_periodic_task(scheduled_task.celery_task_name)
    
    @classmethod
    def activate_task(cls, scheduled_task) -> Optional[PeriodicTask]:
        """Activate a scheduled task."""
        scheduled_task.is_active = True
        scheduled_task.status = 'active'
        scheduled_task.save(update_fields=['is_active', 'status'])
        return cls.sync_task(scheduled_task)
    
    @classmethod
    def deactivate_task(cls, scheduled_task) -> None:
        """Deactivate a scheduled task."""
        cls.delete_task(scheduled_task)
        scheduled_task.is_active = False
        scheduled_task.status = 'paused'
        scheduled_task.celery_task_name = ''
        scheduled_task.save(update_fields=['is_active', 'status', 'celery_task_name'])
    
    @classmethod
    def toggle_task(cls, scheduled_task) -> bool:
        """Toggle a scheduled task's active state. Returns new state."""
        if scheduled_task.is_active:
            cls.deactivate_task(scheduled_task)
            return False
        else:
            cls.activate_task(scheduled_task)
            return True
    
    @classmethod
    def run_task_now(
        cls,
        scheduled_task,
        trigger_type: str = 'manual',
        override_args: list = None,
        override_kwargs: dict = None,
    ):
        """
        Trigger immediate execution of a scheduled task.
        Creates a TaskExecution record and dispatches the Celery task.
        """
        from flows.models import TaskExecution
        
        args = override_args if override_args is not None else scheduled_task.task_args
        kwargs = override_kwargs if override_kwargs is not None else scheduled_task.task_kwargs
        
        execution = TaskExecution.objects.create(
            scheduled_task=scheduled_task,
            tenant=scheduled_task.tenant,
            status=TaskExecution.STATUS_PENDING,
            trigger_type=trigger_type,
            input_data={'args': args, 'kwargs': kwargs},
        )
        
        from flows.tasks import execute_scheduled_task_immediate
        result = execute_scheduled_task_immediate.delay(
            execution_id=str(execution.id),
            task_name=scheduled_task.task_name,
            task_args=args,
            task_kwargs=kwargs,
        )
        
        execution.celery_task_id = result.id
        execution.save(update_fields=['celery_task_id'])
        
        return execution
