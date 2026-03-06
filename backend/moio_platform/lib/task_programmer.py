"""
task_programmer.py — A compact, production-ready scheduler wrapper for django-celery-beat.

Overview
--------
This module provides a small convenience layer over django-celery-beat to program periodic
tasks (cron, interval) and reliable one-shot tasks (clocked) with:

  • Idempotent, tenant-scoped names (stable upserts).
  • Safe JSON serialization of args/kwargs.
  • Queue routing per scheduled entry.
  • Minimal API surface with sensible defaults.

It assumes your Celery Beat is running with the DB scheduler:

    celery -A <yourproj> beat -l info \
      --scheduler django_celery_beat.schedulers:DatabaseScheduler

Quickstart
----------
1) Choose a global timezone in your Celery config (recommended):

    # settings/celery.py
    app.conf.timezone = "America/Argentina/Buenos_Aires"  # or any IANA tz
    app.conf.enable_utc = True

2) Define your Celery task:

    # tasks.py
    from celery import shared_task

    @shared_task(name="campaigns.tasks.rebuild_index")
    def rebuild_index(tenant_id: str):
        ...

3) Schedule it:

    from datetime import datetime, timedelta
    from task_programmer import TaskProgrammer

    tp = TaskProgrammer(tenant="acme", prefix="moio")

    # Cron: every weekday at 18:30 local time
    ref_cron = tp.cron(
        "campaigns.tasks.rebuild_index",
        minute="30", hour="18", day_of_week="1-5",
        args=["acme"], queue="reports"
    )

    # Interval: every 15 minutes
    ref_int = tp.interval(
        "campaigns.tasks.rebuild_index",
        every=15, period="minutes",
        args=["acme"], queue="maintenance"
    )

    # Clocked (one-shot at exact time, survives restarts)
    ref_clk = tp.clocked(
        "campaigns.tasks.rebuild_index",
        when=datetime.now() + timedelta(hours=2),
        one_off=True,
        args=["acme"], queue="priority"
    )

    # Enable/disable/delete by name
    tp.enable(ref_cron.name, enabled=False)
    tp.delete(ref_int.name)

Design Notes
------------
• Idempotency: The (tenant, base-task-name, schedule-kind, parameters) tuple maps to a
  unique, stable PeriodicTask.name. Re-calling with the same parameters will UPDATE the
  existing PeriodicTask rather than create duplicates.

• Time zones:
  - Cron schedules store timezone on the CrontabSchedule row (uses app.conf.timezone).
  - Clocked schedules accept naive datetimes and treat them as UTC unless tz-aware is provided.
  - Interval schedules are timezone-agnostic (they tick relative to Beat).

• Queue routing: Set `queue=` to route executions to a specific Celery queue.

• Args/kwargs: Serialized to JSON. Keep them JSON-serializable.

Requirements
------------
- celery
- django-celery-beat (with migrations applied)

"""

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone as dt_tz
from typing import Any, Dict, Iterable, Optional, Union

from celery import current_app
from celery.canvas import Signature
from django_celery_beat.models import (
    PeriodicTask, CrontabSchedule, IntervalSchedule, ClockedSchedule
)

__all__ = ["TaskProgrammer", "ProgrammedTaskRef"]


def _hash(s: str) -> str:
    """Return a short, stable SHA1-based hash for name salting."""
    return hashlib.sha1(s.encode()).hexdigest()[:10]


def _aware(dt: datetime) -> datetime:
    """
    Ensure a datetime is timezone-aware.

    If naive, the datetime is interpreted as UTC (to avoid accidental local-time drift).
    This mirrors the common Celery practice of keeping broker/beat timestamps in UTC and
    converting only when rendering UI or building crontab entries.

    Parameters
    ----------
    dt : datetime
        The datetime to normalize.

    Returns
    -------
    datetime
        A timezone-aware datetime (UTC if input was naive).
    """
    return dt if dt.tzinfo else dt.replace(tzinfo=dt_tz.utc)


@dataclass(frozen=True)
class ProgrammedTaskRef:
    """
    Lightweight reference to a scheduled PeriodicTask.

    Attributes
    ----------
    name : str
        The stable, idempotent name of the django-celery-beat PeriodicTask.
        You can store this and re-use it to enable/disable/delete the schedule.
    id : str
        The database id of the PeriodicTask (stringified). Useful for debugging/admin links.
    """
    name: str
    id: str


class TaskProgrammer:
    """
    Program periodic and one-shot tasks into django-celery-beat with idempotent upserts.

    This wrapper centralizes:
      • Name stability (prevents duplicate PeriodicTask rows).
      • Queue routing.
      • JSON serialization for args/kwargs.
      • Tenant scoping for multi-tenant apps.

    Instances can be safely re-used across your service layer.

    Parameters
    ----------
    tenant : Optional[str], default None
        Optional tenant slug/id to prefix names. If provided, all scheduled names become
        `"{prefix}:{tenant}:{base}:{kind}:{salt}"`. Useful to isolate schedules per tenant.
    prefix : str, default "tp"
        A short system prefix to avoid name collisions with other schedulers/components.
    """

    def __init__(self, *, tenant: Optional[str] = None, prefix: str = "tp"):
        self.tenant = tenant
        self.prefix = prefix
        # Note: we read the app timezone for cron entries; intervals ignore tz, clocked uses UTC by default.
        self.tzname = getattr(current_app.conf, "timezone", "UTC")

    # ───────────────────────────────────────── Public API ─────────────────────────────────────────

    def cron(
        self,
        task: Union[str, Signature],
        *,
        minute: str = "0",
        hour: str = "*",
        day_of_week: str = "*",
        day_of_month: str = "*",
        month_of_year: str = "*",
        args: Iterable[Any] = (),
        kwargs: Dict[str, Any] | None = None,
        queue: str | None = None,
        name: str | None = None,
        enabled: bool = True,
    ) -> ProgrammedTaskRef:
        """
        Upsert a cron-based schedule for a Celery task.

        Uses django-celery-beat's CrontabSchedule with the application's timezone
        (`celery.current_app.conf.timezone`). Repeated calls with the same parameters
        will update the existing PeriodicTask instead of creating duplicates.

        Parameters
        ----------
        task : Union[str, Signature]
            Either the dotted task path (e.g., "app.tasks.foo") or a Celery Signature.
        minute, hour, day_of_week, day_of_month, month_of_year : str
            Cron fields as strings (supporting ranges, lists, */n). Examples:
            minute="*/5", hour="18", day_of_week="1-5", day_of_month="*", month_of_year="*".
        args : Iterable[Any], default ()
            Positional args for the task (must be JSON-serializable).
        kwargs : Dict[str, Any] | None, default None
            Keyword args for the task (must be JSON-serializable).
        queue : str | None, default None
            Optional Celery queue name to route runs to (e.g., "reports").
        name : str | None, default None
            Optional human-readable base name. If omitted, derived from the task name.
        enabled : bool, default True
            Whether the schedule should be active immediately.

        Returns
        -------
        ProgrammedTaskRef
            Reference containing the stable name and DB id.

        Raises
        ------
        ValueError
            If args/kwargs are not JSON-serializable.
        """
        sig = self._sig(task, args, kwargs)
        uname = self._unique(name or self._task_name(task), "cron",
                             f"{minute}-{hour}-{day_of_week}-{day_of_month}-{month_of_year}")
        cron, _ = CrontabSchedule.objects.get_or_create(
            minute=str(minute), hour=str(hour), day_of_week=str(day_of_week),
            day_of_month=str(day_of_month), month_of_year=str(month_of_year),
            timezone=self.tzname,
        )
        pt, _ = PeriodicTask.objects.update_or_create(
            name=uname,
            defaults={
                "task": sig.task if isinstance(sig, Signature) else str(task),
                "crontab": cron,
                "interval": None,
                "clocked": None,
                "args": json.dumps(list(sig.args or [])),
                "kwargs": json.dumps(sig.kwargs or {}),
                "enabled": enabled,
                "one_off": False,
                "queue": queue or None,
            },
        )
        return ProgrammedTaskRef(name=uname, id=str(pt.id))

    def interval(
        self,
        task: Union[str, Signature],
        *,
        every: int,
        period: str = "minutes",
        args: Iterable[Any] = (),
        kwargs: Dict[str, Any] | None = None,
        queue: str | None = None,
        name: str | None = None,
        enabled: bool = True,
    ) -> ProgrammedTaskRef:
        """
        Upsert an interval-based schedule for a Celery task.

        Interval schedules execute relative to Beat's clock (timezone-agnostic). Repeated
        calls with the same parameters update the existing PeriodicTask.

        Parameters
        ----------
        task : Union[str, Signature]
            Dotted task path or Celery Signature.
        every : int
            Interval magnitude (e.g., 5).
        period : str, default "minutes"
            One of: "seconds", "minutes", "hours", "days".
        args : Iterable[Any], default ()
            Positional args for the task (JSON-serializable).
        kwargs : Dict[str, Any] | None, default None
            Keyword args for the task (JSON-serializable).
        queue : str | None, default None
            Optional Celery queue name to route runs to.
        name : str | None, default None
            Optional human-readable base name. If omitted, derived from the task name.
        enabled : bool, default True
            Whether the schedule should be active immediately.

        Returns
        -------
        ProgrammedTaskRef
            Reference containing the stable name and DB id.

        Raises
        ------
        ValueError
            If `period` is not one of the supported values or args/kwargs are not JSON-serializable.
        """
        sig = self._sig(task, args, kwargs)
        period_l = period.lower()
        if period_l not in {"seconds", "minutes", "hours", "days"}:
            raise ValueError("period must be one of: seconds | minutes | hours | days")
        uname = self._unique(name or self._task_name(task), "interval", f"{every}-{period_l}")
        interval, _ = IntervalSchedule.objects.get_or_create(
            every=every,
            period=getattr(IntervalSchedule, period_l.upper()),
        )
        pt, _ = PeriodicTask.objects.update_or_create(
            name=uname,
            defaults={
                "task": sig.task if isinstance(sig, Signature) else str(task),
                "interval": interval,
                "crontab": None,
                "clocked": None,
                "args": json.dumps(list(sig.args or [])),
                "kwargs": json.dumps(sig.kwargs or {}),
                "enabled": enabled,
                "one_off": False,
                "queue": queue or None,
            },
        )
        return ProgrammedTaskRef(name=uname, id=str(pt.id))

    def clocked(
        self,
        task: Union[str, Signature],
        *,
        when: datetime,
        one_off: bool = True,
        args: Iterable[Any] = (),
        kwargs: Dict[str, Any] | None = None,
        queue: str | None = None,
        name: str | None = None,
        enabled: bool = True,
    ) -> ProgrammedTaskRef:
        """
        Upsert a clocked (exact-time) schedule for a Celery task.

        This is the recommended way to schedule one-shot executions reliably via Beat,
        because the schedule is persisted in the DB and survives process restarts.

        Parameters
        ----------
        task : Union[str, Signature]
            Dotted task path or Celery Signature.
        when : datetime
            Execution timestamp. If naive, it is treated as UTC. To use a local timezone,
            pass a tz-aware datetime.
        one_off : bool, default True
            If True, the schedule runs once and is then disabled (django-celery-beat "one_off").
        args : Iterable[Any], default ()
            Positional args (JSON-serializable).
        kwargs : Dict[str, Any] | None, default None
            Keyword args (JSON-serializable).
        queue : str | None, default None
            Optional Celery queue name to route the run to.
        name : str | None, default None
            Optional human-readable base name. If omitted, derived from the task name.
        enabled : bool, default True
            Whether the schedule should be active immediately.

        Returns
        -------
        ProgrammedTaskRef
            Reference containing the stable name and DB id.

        Notes
        -----
        If you call `clocked()` repeatedly with the same (tenant, base name, 'clocked', when)
        combination, the PeriodicTask will be updated rather than duplicated. If the datetime
        changes, a distinct schedule entry is created.

        Raises
        ------
        ValueError
            If args/kwargs are not JSON-serializable.
        """
        sig = self._sig(task, args, kwargs)
        when = _aware(when)
        uname = self._unique(name or self._task_name(task), "clocked", when.isoformat())
        clock = ClockedSchedule.objects.create(clocked_time=when)
        pt, created = PeriodicTask.objects.update_or_create(
            name=uname,
            defaults={
                "task": sig.task if isinstance(sig, Signature) else str(task),
                "clocked": clock,
                "crontab": None,
                "interval": None,
                "args": json.dumps(list(sig.args or [])),
                "kwargs": json.dumps(sig.kwargs or {}),
                "one_off": one_off,
                "enabled": enabled,
                "queue": queue or None,
            },
        )
        # Ensure the PeriodicTask points to the newly created ClockedSchedule if it changed
        if not created and pt.clocked_id != clock.id:
            pt.clocked = clock
            pt.save(update_fields=["clocked"])
        return ProgrammedTaskRef(name=uname, id=str(pt.id))

    def enable(self, name: str, enabled: bool = True) -> bool:
        """
        Enable or disable a scheduled PeriodicTask by name.

        Parameters
        ----------
        name : str
            The stable name returned by `cron/interval/clocked`.
        enabled : bool, default True
            True to enable; False to disable.

        Returns
        -------
        bool
            True if the update succeeded (or no-op); False if an exception occurred.
        """
        try:
            PeriodicTask.objects.filter(name=name).update(enabled=enabled)
            return True
        except Exception:
            return False

    def delete(self, name: str) -> bool:
        """
        Delete a scheduled PeriodicTask by name.

        Parameters
        ----------
        name : str
            The stable name returned by `cron/interval/clocked`.

        Returns
        -------
        bool
            True if the deletion succeeded (or no rows matched); False if an exception occurred.

        Notes
        -----
        Deleting the PeriodicTask will not cascade-delete the associated schedule rows
        (Crontab/Interval/Clocked) unless your DB is configured to do so. This matches
        django-celery-beat defaults (schedules are typically reused).
        """
        try:
            PeriodicTask.objects.filter(name=name).delete()
            return True
        except Exception:
            return False

    def exists(self, name: str) -> bool:
        """
        Check whether a PeriodicTask exists by name.

        Parameters
        ----------
        name : str
            The stable name used for the schedule.

        Returns
        -------
        bool
            True if a matching PeriodicTask exists, False otherwise.
        """
        return PeriodicTask.objects.filter(name=name).exists()

    # ───────────────────────────────────────── Internals ─────────────────────────────────────────

    def _sig(self, task: Union[str, Signature], args, kwargs) -> Signature:
        """
        Normalize to a Celery Signature, merging any provided args/kwargs with the signature.

        Parameters
        ----------
        task : Union[str, Signature]
            Dotted task path (string) or an existing Signature object.
        args : Iterable[Any]
            Additional positional args to append.
        kwargs : Dict[str, Any] | None
            Additional keyword args to merge.

        Returns
        -------
        Signature
            A signature with merged args/kwargs.

        Raises
        ------
        ValueError
            If args/kwargs cannot be JSON-serialized later by the scheduler.
        """
        if isinstance(task, Signature):
            return Signature(
                task.task,
                args=list(task.args or []) + list(args or ()),
                kwargs={**(task.kwargs or {}), **(kwargs or {})},
                options=task.options,
            )
        return current_app.signature(task, args=list(args or ()), kwargs=kwargs or {})

    def _task_name(self, task: Union[str, Signature]) -> str:
        """Derive a short base name from a dotted task path or a Signature."""
        return task.task if isinstance(task, Signature) else task.split(".")[-1]

    def _unique(self, base: str, kind: str, extra: str) -> str:
        """
        Build a stable, idempotent PeriodicTask.name.

        Format:
            "{prefix}:{tenant?}{base}:{kind}:{salt}"

        Where `salt` is a short SHA1 over (tenant, base, kind, extra) ensuring that
        changing schedule parameters yields a new name, while reusing the same params
        upserts the existing PeriodicTask.

        Parameters
        ----------
        base : str
            Base name (defaults to the task's short name if not provided by caller).
        kind : str
            One of "cron" | "interval" | "clocked".
        extra : str
            A deterministic string representing the schedule parameters, e.g. the
            cron tuple or interval fields or an ISO datetime for clocked.

        Returns
        -------
        str
            The final unique, tenant-scoped name.
        """
        tenant = f"{self.tenant}:" if self.tenant else ""
        salt = _hash(f"{tenant}{base}|{kind}|{extra}")
        return f"{self.prefix}:{tenant}{base}:{kind}:{salt}"
