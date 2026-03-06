from __future__ import annotations

import json
import logging
from datetime import datetime, timezone as dt_timezone
from typing import Optional

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django_celery_beat.models import ClockedSchedule, CrontabSchedule, IntervalSchedule, PeriodicTask

from .models import Robot

logger = logging.getLogger(__name__)


class RobotScheduleService:
    TASK_NAME_PREFIX = "robot_schedule_"
    TASK_PATH = "robots.tasks.execute_scheduled_robot"

    @classmethod
    def get_task_name(cls, robot_id: str) -> str:
        return f"{cls.TASK_NAME_PREFIX}{robot_id}"

    @classmethod
    def sync_robot(cls, robot: Robot) -> Optional[PeriodicTask]:
        task_name = cls.get_task_name(str(robot.id))
        schedule = robot.schedule or {}
        kind = schedule.get("kind")

        if not robot.enabled or not kind:
            cls.delete_task(task_name)
            return None

        kwargs = json.dumps({"robot_id": str(robot.id)})
        with transaction.atomic():
            if kind == "cron":
                task = cls._sync_cron(robot, task_name, kwargs, schedule)
            elif kind == "interval":
                task = cls._sync_interval(robot, task_name, kwargs, schedule)
            elif kind == "one_off":
                task = cls._sync_one_off(robot, task_name, kwargs, schedule)
            else:
                raise ValueError(f"Unsupported schedule.kind: {kind}")
        return task

    @classmethod
    def _sync_cron(cls, robot: Robot, task_name: str, kwargs: str, schedule: dict) -> PeriodicTask:
        expr = (schedule.get("expr") or "").strip()
        tz_name = schedule.get("tz") or "UTC"
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError("schedule.expr must contain 5 cron parts")
        minute, hour, day_of_month, month, day_of_week = parts
        crontab, _ = CrontabSchedule.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month,
            day_of_week=day_of_week,
            timezone=tz_name,
        )
        task, _ = PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                "task": cls.TASK_PATH,
                "kwargs": kwargs,
                "crontab": crontab,
                "interval": None,
                "clocked": None,
                "enabled": True,
                "one_off": False,
                "description": f"Robot schedule for {robot.slug}",
            },
        )
        return task

    @classmethod
    def _sync_interval(cls, robot: Robot, task_name: str, kwargs: str, schedule: dict) -> PeriodicTask:
        seconds = int(schedule.get("seconds") or 0)
        if seconds <= 0:
            raise ValueError("schedule.seconds must be > 0 for interval schedules")
        interval, _ = IntervalSchedule.objects.get_or_create(every=seconds, period=IntervalSchedule.SECONDS)
        task, _ = PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                "task": cls.TASK_PATH,
                "kwargs": kwargs,
                "interval": interval,
                "crontab": None,
                "clocked": None,
                "enabled": True,
                "one_off": False,
                "description": f"Robot schedule for {robot.slug}",
            },
        )
        return task

    @classmethod
    def _sync_one_off(cls, robot: Robot, task_name: str, kwargs: str, schedule: dict) -> PeriodicTask:
        run_at = schedule.get("run_at")
        if not run_at:
            raise ValueError("schedule.run_at is required for one_off")
        run_at_dt: datetime | None
        if isinstance(run_at, datetime):
            run_at_dt = run_at
        elif isinstance(run_at, str):
            run_at_dt = parse_datetime(run_at)
        else:
            run_at_dt = None
        if not run_at_dt:
            raise ValueError("schedule.run_at must be an ISO datetime string (or datetime) for one_off")
        if timezone.is_naive(run_at_dt):
            run_at_dt = run_at_dt.replace(tzinfo=dt_timezone.utc)

        clocked, _ = ClockedSchedule.objects.get_or_create(clocked_time=run_at_dt)
        task, _ = PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                "task": cls.TASK_PATH,
                "kwargs": kwargs,
                "clocked": clocked,
                "interval": None,
                "crontab": None,
                "enabled": True,
                "one_off": True,
                "description": f"Robot schedule for {robot.slug}",
            },
        )
        return task

    @classmethod
    def delete_task(cls, task_name: str) -> bool:
        deleted, _ = PeriodicTask.objects.filter(name=task_name).delete()
        return bool(deleted)
