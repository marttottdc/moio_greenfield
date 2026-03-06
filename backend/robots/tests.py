from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from robots.api_views import RobotRunViewSet, RobotSessionViewSet, RobotViewSet
from robots.contracts import (
    apply_plan_patch,
    validate_instruction_payload,
    validate_llm_output_contract,
)
from robots.models import Robot, RobotEvent, RobotRun, RobotSession
from robots.robot_runtime import _normalise_conversation_history
from robots.tasks import _ensure_session, execute_robot_run, execute_scheduled_robot
from portal.models import Tenant


class RobotContractsTests(SimpleTestCase):
    def test_validate_instruction_payload_allows_known_keys(self):
        payload = validate_instruction_payload(
            {
                "instruction_schema_version": 1,
                "instruction": "process leads",
                "objective_override": {"primary": "sales"},
                "queue_items": ["lead_1", "lead_2"],
                "constraints": {"max_messages": 10},
                "metadata": {"source": "api"},
            }
        )
        self.assertEqual(payload["instruction"], "process leads")
        self.assertEqual(payload["queue_items"], ["lead_1", "lead_2"])

    def test_validate_instruction_payload_rejects_unknown_keys(self):
        with self.assertRaises(ValidationError):
            validate_instruction_payload({"unexpected": "value"})

    def test_validate_instruction_payload_rejects_non_string_session_key(self):
        with self.assertRaises(ValidationError):
            validate_instruction_payload({"session_key": {"bad": "type"}})

    def test_validate_llm_output_contract_requires_fields(self):
        with self.assertRaises(ValidationError):
            validate_llm_output_contract({"assistant_message": "ok"})

    def test_apply_plan_patch_enforces_monotonic_cursor(self):
        previous = {"queue": {"items": ["a", "b"], "cursor": 3}}
        with self.assertRaises(ValidationError):
            apply_plan_patch(previous, {"queue": {"cursor": 2}})

    def test_apply_plan_patch_enforces_budget_decrement(self):
        previous = {"budgets": {"daily_tokens_remaining": 100}}
        with self.assertRaises(ValidationError):
            apply_plan_patch(previous, {"budgets": {"daily_tokens_remaining": 120}})

    def test_apply_plan_patch_rejects_blocked_until_beyond_window_for_naive_datetime(self):
        blocked_until = (timezone.now() + timedelta(days=31)).replace(tzinfo=None).isoformat(timespec="seconds")

        with self.assertRaisesMessage(ValidationError, "blocked_until exceeds max allowed delay window"):
            apply_plan_patch({}, {"state": {"blocked_until": blocked_until}})


class RobotSessionKeyPrefixTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Robots Session Tenant",
            enabled=True,
            domain="robots-session.local",
        )
        self.robot = Robot.objects.create(
            tenant=self.tenant,
            name="Session Prefix Robot",
            slug="session-prefix-robot",
        )

    def _create_run(self, *, trigger_source: str) -> RobotRun:
        return RobotRun.objects.create(
            robot=self.robot,
            status=RobotRun.STATUS_PENDING,
            trigger_source=trigger_source,
            trigger_payload={},
        )

    def test_ensure_session_uses_trigger_source_prefix_for_known_sources(self):
        for trigger_source in ("manual", "schedule", "event", "campaign"):
            with self.subTest(trigger_source=trigger_source):
                run = self._create_run(trigger_source=trigger_source)
                session = _ensure_session(run)
                self.assertEqual(session.session_key, f"{trigger_source}:{run.id}")

    def test_ensure_session_uses_manual_prefix_for_unknown_sources(self):
        run = self._create_run(trigger_source="webhook")
        session = _ensure_session(run)
        self.assertEqual(session.session_key, f"manual:{run.id}")


class RobotRuntimeConversationHistoryTests(SimpleTestCase):
    def test_normalise_conversation_history_skips_tool_role_and_stringifies_content(self):
        transcript = [
            {"role": "user", "content": "hello"},
            {"role": "tool", "content": {"tool_calls": [{"name": "lookup"}]}},
            {"role": "assistant", "content": {"status": "ok"}},
            {"role": "system", "content": "keep going"},
        ]

        history = _normalise_conversation_history(transcript)

        self.assertEqual([item["role"] for item in history], ["user", "assistant", "system"])
        self.assertEqual(history[0]["content"], "hello")
        self.assertEqual(history[1]["content"], '{"status": "ok"}')
        self.assertEqual(history[2]["content"], "keep going")


class RobotScheduledTaskSessionKeyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Robots Scheduled Tenant",
            enabled=True,
            domain="robots-scheduled.local",
        )
        self.robot = Robot.objects.create(
            tenant=self.tenant,
            name="Scheduled Prefix Robot",
            slug="scheduled-prefix-robot",
            model_config={"max_iterations": 1},
        )

    @patch("robots.tasks.execute_robot_run.apply_async", return_value=None)
    @patch("robots.tasks.WebSocketEventPublisher.publish_robot_run_event", return_value=True)
    def test_execute_scheduled_robot_sets_and_uses_schedule_session_key(self, _publish_mock, _apply_async_mock):
        response = execute_scheduled_robot(str(self.robot.id))

        self.assertEqual(response["status"], "enqueued")
        run = RobotRun.objects.get(id=response["run_id"])
        self.assertEqual(run.trigger_source, "schedule")
        self.assertEqual((run.trigger_payload or {}).get("session_key"), f"schedule:{run.id}")

        class _FakeRuntime:
            def step(self, *, run, session, iteration, max_iterations, instruction_payload):
                return (
                    {
                        "assistant_message": "ok",
                        "tool_calls": [],
                        "plan_patch": None,
                        "stop_reason": "completed",
                    },
                    [],
                )

        with patch("robots.tasks.RobotRuntime.for_robot", return_value=_FakeRuntime()):
            result = execute_robot_run(str(run.id))
        self.assertEqual(result["status"], RobotRun.STATUS_SUCCESS)

        run.refresh_from_db()
        self.assertIsNotNone(run.session_id)
        self.assertEqual(run.session.session_key, f"schedule:{run.id}")


class RobotTaskCancellationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Robots Tenant",
            enabled=True,
            domain="robots.local",
        )
        self.robot = Robot.objects.create(
            tenant=self.tenant,
            name="Cancellation Test Robot",
            slug="cancellation-test-robot",
            model_config={"max_iterations": 3},
        )

    @patch("robots.tasks.WebSocketEventPublisher.publish_robot_run_event", return_value=True)
    def test_execute_robot_run_detects_db_cancel_requested_mid_loop(self, _publish_mock):
        run = RobotRun.objects.create(
            robot=self.robot,
            status=RobotRun.STATUS_PENDING,
            trigger_source="manual",
            trigger_payload={
                "instruction_schema_version": 1,
                "instruction": "keep working",
                "metadata": {},
            },
        )

        class _FakeRuntime:
            def step(self, *, run, session, iteration, max_iterations, instruction_payload):
                if iteration == 1:
                    RobotRun.objects.filter(id=run.id).update(cancel_requested_at=timezone.now())
                return (
                    {
                        "assistant_message": f"iteration {iteration}",
                        "tool_calls": [],
                        "plan_patch": None,
                        "stop_reason": "continue",
                    },
                    [],
                )

        with patch("robots.tasks.RobotRuntime.for_robot", return_value=_FakeRuntime()):
            result = execute_robot_run(str(run.id))

        run.refresh_from_db()
        self.assertEqual(result["status"], RobotRun.STATUS_CANCELLED)
        self.assertEqual(run.status, RobotRun.STATUS_CANCELLED)

        event_types = list(RobotEvent.objects.filter(run=run).values_list("event_type", flat=True))
        self.assertIn("lifecycle.cancelled", event_types)
        self.assertNotIn("lifecycle.completed", event_types)


class RobotTaskIterationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Robots Iteration Tenant",
            enabled=True,
            domain="robots-iteration.local",
        )
        self.robot = Robot.objects.create(
            tenant=self.tenant,
            name="Iteration Test Robot",
            slug="iteration-test-robot",
            model_config={"max_iterations": 3},
        )

    @patch("robots.tasks.WebSocketEventPublisher.publish_robot_run_event", return_value=True)
    def test_execute_robot_run_default_scaffold_uses_configured_iterations(self, _publish_mock):
        run = RobotRun.objects.create(
            robot=self.robot,
            status=RobotRun.STATUS_PENDING,
            trigger_source="manual",
            trigger_payload={
                "instruction_schema_version": 1,
                "instruction": "iterate using scaffold",
                "metadata": {},
            },
        )

        class _FakeRuntime:
            def step(self, *, run, session, iteration, max_iterations, instruction_payload):
                stop_reason = "completed" if iteration >= max_iterations else "continue"
                return (
                    {
                        "assistant_message": f"iteration {iteration}",
                        "tool_calls": [],
                        "plan_patch": None,
                        "stop_reason": stop_reason,
                    },
                    [],
                )

        with patch("robots.tasks.RobotRuntime.for_robot", return_value=_FakeRuntime()):
            result = execute_robot_run(str(run.id))
        run.refresh_from_db()

        self.assertEqual(result["status"], RobotRun.STATUS_SUCCESS)
        self.assertEqual(run.status, RobotRun.STATUS_SUCCESS)
        self.assertEqual(run.usage["iterations"], 3)
        self.assertEqual(run.usage["llm_calls"], 3)
        self.assertEqual(run.output_data["stop_reason"], "completed")
        self.assertEqual(RobotEvent.objects.filter(run=run, event_type="assistant.message").count(), 3)
        self.assertEqual(RobotEvent.objects.filter(run=run, event_type="metrics").count(), 3)


class RobotViewSetAtomicityTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Robots Atomicity Tenant",
            enabled=True,
            domain="robots-atomicity.local",
        )
        self.factory = APIRequestFactory()
        self.create_view = RobotViewSet.as_view({"post": "create"})
        self.partial_update_view = RobotViewSet.as_view({"patch": "partial_update"})
        # Keep user unauthenticated so create() does not try to bind created_by to a non-User object.
        self.user = SimpleNamespace(tenant=self.tenant, is_authenticated=False)

    def test_create_rolls_back_robot_when_schedule_sync_fails(self):
        payload = {
            "name": "Atomicity Create Robot",
            "slug": "atomicity-create-robot",
            "schedule": {"kind": "unsupported"},
        }
        request = self.factory.post("/api/v1/robots/", payload, format="json")
        force_authenticate(request, user=self.user)

        response = self.create_view(request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Robot.objects.filter(tenant=self.tenant, slug="atomicity-create-robot").exists())

    def test_partial_update_rolls_back_changes_when_schedule_sync_fails(self):
        robot = Robot.objects.create(
            tenant=self.tenant,
            name="Atomicity Update Robot",
            slug="atomicity-update-robot",
            schedule={"kind": "interval", "seconds": 60},
        )
        payload = {
            "name": "Should Not Persist",
            "schedule": {"kind": "unsupported"},
        }
        request = self.factory.patch(f"/api/v1/robots/{robot.id}/", payload, format="json")
        force_authenticate(request, user=self.user)

        response = self.partial_update_view(request, pk=str(robot.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        robot.refresh_from_db()
        self.assertEqual(robot.name, "Atomicity Update Robot")
        self.assertEqual(robot.schedule, {"kind": "interval", "seconds": 60})


class RobotViewSetPaginationApiTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Robots Detail API Tenant",
            enabled=True,
            domain="robots-detail-api.local",
        )
        self.robot = Robot.objects.create(
            tenant=self.tenant,
            name="Robot Detail API Test Robot",
            slug="robot-detail-api-test-robot",
        )
        self.other_tenant = Tenant.objects.create(
            nombre="Robots Detail API Other Tenant",
            enabled=True,
            domain="robots-detail-api-other.local",
        )
        other_robot = Robot.objects.create(
            tenant=self.other_tenant,
            name="Other Tenant Detail Robot",
            slug="other-tenant-detail-robot",
        )

        for idx in range(3):
            RobotRun.objects.create(
                robot=self.robot,
                status=RobotRun.STATUS_PENDING,
                trigger_source="manual",
                trigger_payload={"index": idx},
            )
            RobotEvent.objects.create(
                robot=self.robot,
                event_type=f"robot.detail.event.{idx}",
                payload={"index": idx},
            )

        RobotRun.objects.create(
            robot=other_robot,
            status=RobotRun.STATUS_PENDING,
            trigger_source="manual",
            trigger_payload={"seed": "foreign"},
        )
        RobotEvent.objects.create(
            robot=other_robot,
            event_type="robot.detail.event.foreign",
            payload={"seed": "foreign"},
        )

        self.factory = APIRequestFactory()
        self.runs_view = RobotViewSet.as_view({"get": "runs"})
        self.events_view = RobotViewSet.as_view({"get": "events"})
        self.user = SimpleNamespace(tenant=self.tenant, is_authenticated=True)

    def test_runs_clamps_invalid_pagination_values(self):
        request = self.factory.get(
            f"/api/v1/robots/{self.robot.id}/runs/",
            {"limit": "not-a-number", "offset": "-10"},
        )
        force_authenticate(request, user=self.user)

        response = self.runs_view(request, pk=str(self.robot.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data

        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["limit"], 50)
        self.assertEqual(payload["offset"], 0)

    def test_events_clamps_invalid_pagination_values(self):
        request = self.factory.get(
            f"/api/v1/robots/{self.robot.id}/events/",
            {"limit": "not-a-number", "offset": "-10"},
        )
        force_authenticate(request, user=self.user)

        response = self.events_view(request, pk=str(self.robot.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data

        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["limit"], 100)
        self.assertEqual(payload["offset"], 0)

    def test_runs_and_events_cap_limit_to_prevent_large_fetches(self):
        runs_request = self.factory.get(
            f"/api/v1/robots/{self.robot.id}/runs/",
            {"limit": "1000", "offset": "0"},
        )
        force_authenticate(runs_request, user=self.user)
        runs_response = self.runs_view(runs_request, pk=str(self.robot.id))
        self.assertEqual(runs_response.status_code, status.HTTP_200_OK)
        self.assertEqual(runs_response.data["limit"], 100)
        self.assertEqual(runs_response.data["offset"], 0)

        events_request = self.factory.get(
            f"/api/v1/robots/{self.robot.id}/events/",
            {"limit": "1000", "offset": "0"},
        )
        force_authenticate(events_request, user=self.user)
        events_response = self.events_view(events_request, pk=str(self.robot.id))
        self.assertEqual(events_response.status_code, status.HTTP_200_OK)
        self.assertEqual(events_response.data["limit"], 100)
        self.assertEqual(events_response.data["offset"], 0)


class RobotRunListApiTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Robots Run API Tenant",
            enabled=True,
            domain="robots-run-api.local",
        )
        self.robot = Robot.objects.create(
            tenant=self.tenant,
            name="Robots Run API Test Robot",
            slug="robots-run-api-test-robot",
        )
        self.other_tenant = Tenant.objects.create(
            nombre="Robots Run API Other Tenant",
            enabled=True,
            domain="robots-run-api-other.local",
        )
        other_robot = Robot.objects.create(
            tenant=self.other_tenant,
            name="Other Tenant Run Robot",
            slug="other-tenant-run-robot",
        )
        self.foreign_run = RobotRun.objects.create(
            robot=other_robot,
            status=RobotRun.STATUS_PENDING,
            trigger_source="manual",
            trigger_payload={"seed": "foreign"},
        )

        self.factory = APIRequestFactory()
        self.list_view = RobotRunViewSet.as_view({"get": "list"})
        self.user = SimpleNamespace(tenant=self.tenant, is_authenticated=True)

        self.runs = []
        now = timezone.now()
        for idx in range(3):
            run = RobotRun.objects.create(
                robot=self.robot,
                status=RobotRun.STATUS_PENDING,
                trigger_source="manual",
                trigger_payload={"index": idx},
            )
            RobotRun.objects.filter(id=run.id).update(started_at=now + timedelta(minutes=idx))
            run.refresh_from_db()
            self.runs.append(run)

    def test_list_is_paginated_and_scoped_to_tenant(self):
        request = self.factory.get("/api/v1/robots/runs/", {"limit": 2, "offset": 1})
        force_authenticate(request, user=self.user)

        response = self.list_view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = response.data
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["limit"], 2)
        self.assertEqual(payload["offset"], 1)

        expected_ids = [str(self.runs[1].id), str(self.runs[0].id)]
        returned_ids = [item["id"] for item in payload["runs"]]
        self.assertEqual(returned_ids, expected_ids)
        self.assertNotIn(str(self.foreign_run.id), returned_ids)

    def test_list_clamps_invalid_pagination_values(self):
        request = self.factory.get(
            "/api/v1/robots/runs/",
            {"limit": "not-a-number", "offset": "-10"},
        )
        force_authenticate(request, user=self.user)

        response = self.list_view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data

        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["limit"], 50)
        self.assertEqual(payload["offset"], 0)

    def test_list_caps_limit_to_prevent_large_fetches(self):
        request = self.factory.get("/api/v1/robots/runs/", {"limit": "1000", "offset": "0"})
        force_authenticate(request, user=self.user)

        response = self.list_view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data

        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["limit"], 100)
        self.assertEqual(payload["offset"], 0)


class RobotSessionListApiTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Robots API Tenant",
            enabled=True,
            domain="robots-api.local",
        )
        self.robot = Robot.objects.create(
            tenant=self.tenant,
            name="Robots API Test Robot",
            slug="robots-api-test-robot",
        )
        self.other_tenant = Tenant.objects.create(
            nombre="Robots API Other Tenant",
            enabled=True,
            domain="robots-api-other.local",
        )
        other_robot = Robot.objects.create(
            tenant=self.other_tenant,
            name="Other Tenant Robot",
            slug="other-tenant-robot",
        )
        RobotSession.objects.create(
            robot=other_robot,
            session_key="manual:foreign",
            metadata={"seed": "foreign"},
            transcript=[{"role": "assistant", "content": "foreign"}],
            intent_state={},
        )

        self.factory = APIRequestFactory()
        self.list_view = RobotSessionViewSet.as_view({"get": "list"})
        self.retrieve_view = RobotSessionViewSet.as_view({"get": "retrieve"})
        self.user = SimpleNamespace(tenant=self.tenant, is_authenticated=True)

        self.sessions = []
        now = timezone.now()
        for idx in range(3):
            session = RobotSession.objects.create(
                robot=self.robot,
                session_key=f"manual:test-{idx}",
                metadata={"index": idx},
                transcript=[{"role": "assistant", "content": f"entry-{idx}-{n}"} for n in range(idx + 1)],
                intent_state={"step": idx},
            )
            RobotSession.objects.filter(id=session.id).update(updated_at=now + timedelta(minutes=idx))
            session.refresh_from_db()
            self.sessions.append(session)

    def test_list_is_paginated_and_omits_transcript_payload(self):
        request = self.factory.get("/api/v1/robots/sessions/", {"limit": 2, "offset": 1})
        force_authenticate(request, user=self.user)

        response = self.list_view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = response.data
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["limit"], 2)
        self.assertEqual(payload["offset"], 1)

        expected_ids = [str(self.sessions[1].id), str(self.sessions[0].id)]
        returned_ids = [item["id"] for item in payload["sessions"]]
        self.assertEqual(returned_ids, expected_ids)

        expected_entries = {str(session.id): len(session.transcript) for session in self.sessions}
        for session_payload in payload["sessions"]:
            self.assertNotIn("transcript", session_payload)
            self.assertEqual(session_payload["transcript_entries"], expected_entries[session_payload["id"]])

    def test_list_clamps_invalid_pagination_values(self):
        request = self.factory.get(
            "/api/v1/robots/sessions/",
            {"limit": "not-a-number", "offset": "-10"},
        )
        force_authenticate(request, user=self.user)

        response = self.list_view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data

        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["limit"], 50)
        self.assertEqual(payload["offset"], 0)

    def test_retrieve_keeps_full_transcript(self):
        target = self.sessions[-1]
        request = self.factory.get(f"/api/v1/robots/sessions/{target.id}/")
        force_authenticate(request, user=self.user)

        response = self.retrieve_view(request, pk=str(target.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("transcript", response.data["session"])
        self.assertEqual(len(response.data["session"]["transcript"]), len(target.transcript))
