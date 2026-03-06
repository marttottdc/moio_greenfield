import json
import textwrap
import uuid

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import translation
from django.utils.text import slugify

from flows.models import FlowScript, FlowScriptLog, FlowScriptRun, FlowScriptVersion
from portal.models import MoioUser, Tenant, TenantConfiguration
from portal.signals import create_internal_contact


class FlowScriptViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        post_save.disconnect(create_internal_contact, sender=get_user_model())
        self.addCleanup(
            lambda: post_save.connect(create_internal_contact, sender=get_user_model())
        )
        translation.activate("en")
        self.addCleanup(translation.deactivate)

        self.tenant = Tenant.objects.create(
            nombre="Acme Corp",
            enabled=True,
            domain="acme.test",
        )
        TenantConfiguration.objects.get_or_create(tenant=self.tenant)
        self.user = MoioUser.objects.create_user(
            email="user@example.com",
            username="user",
            password="secret",
            tenant=self.tenant,
        )
        self.client.force_login(self.user)

    def _create_script(self, *, publish=False, code=None, parameters=None) -> FlowScript:
        script = FlowScript.objects.create(
            tenant=self.tenant,
            name="Sample script",
            slug=f"sample-{uuid.uuid4().hex[:6]}",
            description="",
        )
        FlowScriptVersion.objects.create(
            script=script,
            tenant=self.tenant,
            flow=None,
            version_number=1,
            code=code
            or textwrap.dedent(
                """
                def main(params):
                    return params
                """
            ).strip(),
            parameters=parameters or {"foo": "bar"},
        )
        if publish:
            script.latest_version.publish()
        return script

    def test_script_list_renders_existing_scripts(self):
        script = self._create_script()
        script.name = "List me"
        script.save(update_fields=["name"])

        response = self.client.get(reverse("flows:script_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "List me")

    def test_validate_endpoint_reports_errors(self):
        payload = {
            "name": "",
            "code": "def main(",
            "params_text": "{invalid}",
        }
        response = self.client.post(
            reverse("flows:script_validate"),
            data={
                "name": payload["name"],
                "code": payload["code"],
                "params": payload["params_text"],
            },
        )

        self.assertEqual(response.status_code, 400)
        content = response.content.decode("utf-8")
        self.assertIn("Name is required", content)
        self.assertIn("Invalid JSON", content)

    def test_api_script_validate_reports_errors(self):
        payload = {
            "name": "",
            "code": "def main(",
            "params": "{invalid}",
        }

        response = self.client.post(
            reverse("flows_api:api_script_validate"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("name", data["errors"])
        self.assertIn("params", data["errors"])

    def test_api_script_validate_accepts_valid_payload(self):
        payload = {
            "name": "Sample",
            "description": "desc",
            "code": "def main(params):\n    return params",
            "params": {"foo": "bar"},
        }

        response = self.client.post(
            reverse("flows_api:api_script_validate"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["params"], payload["params"])

    def test_save_draft_creates_script(self):
        payload = {
            "name": "Draft name",
            "description": "Draft description",
            "code": "def main(params):\n    return params",
            "params": {"a": 1},
        }

        initial_count = FlowScript.objects.count()

        response = self.client.post(
            reverse("flows:script_save_new"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(FlowScript.objects.count(), initial_count + 1)
        script = (
            FlowScript.objects.filter(name="Draft name")
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(script)
        self.assertEqual(script.versions.count(), 1)
        version = script.latest_version
        self.assertEqual(version.code.strip(), payload["code"])
        self.assertEqual(version.parameters, payload["params"])
        data = response.json()
        self.assertIn("script", data)
        self.assertEqual(data["script"]["name"], "Draft name")
        self.assertEqual(
            data["script"]["latest_version"]["parameters"], payload["params"]
        )

    def test_publish_uses_latest_version_by_default(self):
        draft_payload = {
            "name": "Updated name",
            "description": "Published description",
            "code": "def main(params):\n    return params",
            "params": {"foo": "bar"},
        }

        draft_response = self.client.post(
            reverse("flows:script_save_new"),
            data=json.dumps(draft_payload),
            content_type="application/json",
        )

        self.assertEqual(draft_response.status_code, 200)
        draft_data = draft_response.json()["script"]
        script_id = uuid.UUID(draft_data["id"])

        publish_payload = {**draft_payload, "script_id": str(script_id)}
        response = self.client.post(
            reverse("flows:script_publish"),
            data=json.dumps(publish_payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        script = FlowScript.objects.get(id=script_id)
        self.assertEqual(script.versions.count(), 1)
        published_version = script.published_version
        self.assertIsNotNone(published_version)
        self.assertEqual(published_version.parameters, draft_payload["params"])
        self.assertEqual(published_version.version_number, 1)
        data = response.json()
        self.assertTrue(data["script"]["is_published"])
        self.assertEqual(
            data["script"]["published_version"]["version"],
            published_version.version_number,
        )
        self.assertEqual(
            data["script"]["published_version"]["id"], str(published_version.id)
        )

    def test_publish_creates_new_version_when_latest_is_published(self):
        script = self._create_script(publish=True)
        payload = {
            "script_id": str(script.id),
            "name": "Sample script",
            "description": "Updated after publish",
            "code": "def main(params):\n    return {'foo': params.get('foo', 0) + 1}",
            "params": {"foo": 1},
            "notes": "Re-release",
        }

        response = self.client.post(
            reverse("flows:script_publish"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        script.refresh_from_db()
        self.assertEqual(script.versions.count(), 2)
        latest_version = script.latest_version
        self.assertEqual(latest_version.version_number, 2)
        self.assertEqual(latest_version.parameters, payload["params"])
        self.assertEqual(latest_version.code, payload["code"])
        self.assertEqual(latest_version.notes, payload["notes"])
        published_version = script.published_version
        self.assertEqual(published_version.id, latest_version.id)
        self.assertEqual(published_version.version_number, 2)
        data = response.json()["script"]
        self.assertTrue(data["is_published"])
        self.assertEqual(
            data["published_version"]["version"], published_version.version_number
        )
        self.assertEqual(
            data["published_version"]["id"], str(published_version.id)
        )

    def test_publish_can_target_specific_version(self):
        script = self._create_script()
        FlowScriptVersion.objects.create(
            script=script,
            tenant=script.tenant,
            flow=script.flow,
            version_number=2,
            code="def main(params):\n    return {'v': 2}",
            parameters={"foo": "baz"},
        )
        version_one = script.versions.get(version_number=1)

        payload = {
            "script_id": str(script.id),
            "version_id": str(version_one.id),
            "name": script.name,
            "description": script.description,
            "code": version_one.code,
            "params": version_one.parameters,
        }

        response = self.client.post(
            reverse("flows:script_publish"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        script.refresh_from_db()
        self.assertEqual(script.versions.count(), 2)
        published_version = script.published_version
        self.assertEqual(published_version.id, version_one.id)
        self.assertTrue(response.json()["script"]["is_published"])
        self.assertEqual(
            response.json()["script"]["published_version"]["id"], str(version_one.id)
        )

    def test_save_draft_via_htmx_creates_script(self):
        params = {"alpha": 1}
        code = "def main(params):\n    return params"
        response = self.client.post(
            reverse("flows:script_save_new"),
            data={
                "name": "HTMX draft",
                "description": "From builder",
                "params": json.dumps(params),
                "code": code,
                "notes": "Initial notes",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "script-saved")
        payload = response.json()
        script_data = payload["script"]
        script = FlowScript.objects.get(id=uuid.UUID(script_data["id"]))

        self.assertEqual(script.tenant, self.tenant)
        self.assertEqual(script.slug, slugify("HTMX draft"))
        self.assertEqual(script.latest_version.version_number, 1)
        self.assertEqual(script.latest_version.notes, "Initial notes")
        self.assertEqual(script.latest_version.parameters, params)

        self.assertEqual(script_data["latest_version"]["code"], code)
        self.assertEqual(script_data["latest_version"]["parameters"], params)
        pretty_params = json.dumps(params, indent=2, ensure_ascii=False)
        self.assertEqual(script_data["latest_version"]["parameters_text"], pretty_params)
        self.assertEqual(script_data["params_text"], pretty_params)

    def test_save_draft_via_htmx_updates_script(self):
        script = self._create_script()
        original_version_id = script.latest_version.id
        params = {"value": 42}
        code = "def main(params):\n    return {'value': params.get('value', 0)}"

        response = self.client.post(
            reverse("flows:script_save_new"),
            data={
                "script_id": str(script.id),
                "name": "Updated HTMX",
                "description": "Updated description",
                "params": json.dumps(params),
                "code": code,
                "notes": "Second version",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "script-saved")

        script.refresh_from_db()
        self.assertEqual(script.name, "Updated HTMX")
        self.assertEqual(script.description, "Updated description")
        self.assertEqual(script.versions.count(), 2)
        self.assertTrue(
            FlowScriptVersion.objects.filter(id=original_version_id).exists()
        )

        latest_version = script.latest_version
        self.assertEqual(latest_version.version_number, 2)
        self.assertEqual(latest_version.parameters, params)
        self.assertEqual(latest_version.notes, "Second version")

        data = response.json()["script"]
        self.assertEqual(data["latest_version"]["version"], 2)
        self.assertEqual(data["latest_version"]["parameters"], params)
        self.assertEqual(data["latest_version"]["code"], code)
        pretty_params = json.dumps(params, indent=2, ensure_ascii=False)
        self.assertEqual(data["latest_version"]["parameters_text"], pretty_params)
        self.assertEqual(data["params_text"], pretty_params)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_run_creates_successful_run_and_logs(self):
        script = self._create_script(
            publish=True,
            code=textwrap.dedent(
                """
                def main(params):
                    total = params.get("a", 0) + params.get("b", 0)
                    log(f"total={total}")
                    return {"total": total}
                """
            ).strip(),
        )

        response = self.client.post(
            reverse("flows:script_run"),
            data={
                "script_id": str(script.id),
                "params": json.dumps({"a": 1, "b": 2}),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 202)
        run = FlowScriptRun.objects.filter(script=script).order_by("-started_at").first()
        self.assertIsNotNone(run)
        self.assertEqual(run.status, FlowScriptRun.STATUS_SUCCESS)
        self.assertEqual(run.output_payload.get("total"), 3)
        self.assertTrue(
            FlowScriptLog.objects.filter(run=run, message__icontains="Run queued").exists()
        )

        stream_response = self.client.post(
            reverse("flows:script_log_stream", args=[run.id]),
            data={"script_id": str(script.id)},
        )
        chunks = list(stream_response.streaming_content)
        body = b"".join(chunks).decode("utf-8")
        self.assertIn('"type": "log"', body)
        self.assertIn('"type": "status"', body)
