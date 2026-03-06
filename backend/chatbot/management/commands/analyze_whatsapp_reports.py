#!/usr/bin/env python3
"""
Analyze WhatsApp delivery logs (WaMessageLog) and optionally export for reporting.

Output matches the structure of the communications/whatsapp-logs API: one logical
message per msg_id with latest status. Use this to inspect delivery rates,
failures, and volume by tenant, date, origin, or status.

Usage:
  python manage.py analyze_whatsapp_reports
  python manage.py analyze_whatsapp_reports --tenant 1
  python manage.py analyze_whatsapp_reports --start 2025-02-01 --end 2025-02-20
  python manage.py analyze_whatsapp_reports --export csv --output whatsapp_report.csv
  python manage.py analyze_whatsapp_reports --export json --output whatsapp_report.json
"""

from collections import defaultdict
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Analyze WhatsApp delivery logs (WaMessageLog) and optionally export to CSV/JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            type=int,
            dest="tenant_id",
            help="Limit analysis to this tenant ID.",
        )
        parser.add_argument(
            "--start",
            type=str,
            help="Start date: YYYY-MM-DD or ISO datetime (inclusive).",
        )
        parser.add_argument(
            "--end",
            type=str,
            help="End date: YYYY-MM-DD or ISO datetime (inclusive).",
        )
        parser.add_argument(
            "--export",
            choices=["csv", "json"],
            help="Export messages to CSV or JSON (one row per msg_id with latest status).",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="whatsapp_report",
            help="Output file path (without extension if using --export). Default: whatsapp_report",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50_000,
            help="Max number of log rows to load (default 50000). Reduce if memory is tight.",
        )

    def handle(self, *args, **options):
        try:
            from chatbot.models.wa_message_log import WaMessageLog
        except ImportError:
            self.stderr.write(self.style.ERROR("WaMessageLog model not available."))
            return

        tenant_id = options.get("tenant_id")
        start_raw = options.get("start")
        end_raw = options.get("end")
        export_fmt = options.get("export")
        output_path = options.get("output")
        limit = options.get("limit")

        # Parse dates (YYYY-MM-DD or full ISO)
        start_dt = self._parse_date(start_raw) if start_raw else None
        end_dt = self._parse_date(end_raw) if end_raw else None

        qs = WaMessageLog.objects.all().exclude(msg_id__isnull=True).exclude(msg_id__exact="")
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        if start_dt:
            qs = qs.filter(created__gte=start_dt)
        if end_dt:
            qs = qs.filter(created__lte=end_dt)

        # Fetch in chronological order per msg_id so we can take last status
        logs = list(
            qs.order_by("msg_id", "timestamp", "created", "updated").values(
                "msg_id",
                "status",
                "origin",
                "type",
                "timestamp",
                "created",
                "user_number",
                "user_name",
                "recipient_id",
                "body",
                "flow_execution_id",
            )[:limit]
        )

        if not logs:
            self.stdout.write("No WhatsApp log entries found for the given filters.")
            return

        # Group by msg_id and keep last status (chronological)
        by_msg: dict = {}
        for row in logs:
            key = row["msg_id"]
            ts = row["timestamp"] or row["created"]
            if key not in by_msg:
                by_msg[key] = {
                    "msg_id": key,
                    "status": row["status"],
                    "origin": row["origin"],
                    "type": row["type"],
                    "timestamp": ts,
                    "created": row["created"],
                    "user_number": row["user_number"],
                    "user_name": row["user_name"],
                    "recipient_id": row["recipient_id"],
                    "body": (row["body"] or "")[:200],
                    "flow_execution_id": str(row["flow_execution_id"]) if row["flow_execution_id"] else None,
                }
            else:
                if ts and (by_msg[key]["timestamp"] is None or ts >= by_msg[key]["timestamp"]):
                    by_msg[key].update(
                        status=row["status"],
                        origin=row["origin"],
                        type=row["type"],
                        timestamp=ts,
                        created=row["created"],
                        user_number=row["user_number"] or by_msg[key]["user_number"],
                        user_name=row["user_name"] or by_msg[key]["user_name"],
                        recipient_id=row["recipient_id"] or by_msg[key]["recipient_id"],
                        body=(row["body"] or by_msg[key]["body"] or "")[:200],
                        flow_execution_id=row["flow_execution_id"] or by_msg[key]["flow_execution_id"],
                    )

        messages = list(by_msg.values())
        total_messages = len(messages)

        # Aggregations
        by_status = defaultdict(int)
        by_origin = defaultdict(int)
        by_date = defaultdict(int)
        for m in messages:
            st = m["status"] or "(empty)"
            by_status[st] += 1
            orig = m["origin"] or "(empty)"
            by_origin[orig] += 1
            if m["created"]:
                by_date[m["created"].date().isoformat()] += 1

        # Print summary
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("=== WhatsApp report analysis ==="))
        self.stdout.write(f"  Total log rows read: {len(logs)}")
        self.stdout.write(f"  Unique messages (msg_id): {total_messages}")
        if start_dt or end_dt:
            self.stdout.write(f"  Date range: {start_dt or 'any'} to {end_dt or 'any'}")
        if tenant_id:
            self.stdout.write(f"  Tenant ID: {tenant_id}")
        self.stdout.write("")

        self.stdout.write("  By latest status:")
        for st, count in sorted(by_status.items(), key=lambda x: -x[1]):
            self.stdout.write(f"    {st}: {count}")
        self.stdout.write("")

        self.stdout.write("  By origin:")
        for orig, count in sorted(by_origin.items(), key=lambda x: -x[1]):
            self.stdout.write(f"    {orig}: {count}")
        self.stdout.write("")

        self.stdout.write("  By date (message created):")
        for d, count in sorted(by_date.items(), reverse=True)[:30]:
            self.stdout.write(f"    {d}: {count}")
        if len(by_date) > 30:
            self.stdout.write(f"    ... and {len(by_date) - 30} more dates")
        self.stdout.write("")

        # Delivery-style summary
        delivered = by_status.get("delivered", 0)
        sent = by_status.get("sent", 0)
        read_ = by_status.get("read", 0)
        failed = sum(c for s, c in by_status.items() if s and s.lower() in ("failed", "error", "rejected"))
        self.stdout.write("  Summary:")
        self.stdout.write(f"    delivered: {delivered}  sent: {sent}  read: {read_}")
        self.stdout.write(f"    failed/error/rejected: {failed}")
        self.stdout.write("")

        if export_fmt:
            path = output_path if "." in output_path else f"{output_path}.{export_fmt}"
            if export_fmt == "csv":
                self._export_csv(messages, path)
            else:
                self._export_json(messages, path)
            self.stdout.write(self.style.SUCCESS(f"Exported {total_messages} messages to {path}"))

    def _parse_date(self, value):
        if not value:
            return None
        value = value.strip()
        if len(value) == 10 and value[4] == "-" and value[7] == "-":
            value = f"{value}T00:00:00"
        try:
            return timezone.make_aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except Exception:
            return None

    def _export_csv(self, messages, path):
        import csv

        if not messages:
            return
        keys = list(messages[0].keys())
        for m in messages:
            for k in m:
                if k not in keys:
                    keys.append(k)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for m in messages:
                row = {}
                for k, v in m.items():
                    if hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
                    else:
                        row[k] = v
                w.writerow(row)

    def _export_json(self, messages, path):
        import json

        def _serial(o):
            if hasattr(o, "isoformat"):
                return o.isoformat()
            raise TypeError(type(o).__name__)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2, default=_serial)
