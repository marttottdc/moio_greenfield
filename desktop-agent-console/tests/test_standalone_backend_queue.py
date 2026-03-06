from __future__ import annotations

import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path


if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class _AsyncOpenAI:  # pragma: no cover - import stub for tests
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    openai_stub.AsyncOpenAI = _AsyncOpenAI
    sys.modules["openai"] = openai_stub


from moio_runtime.config import AgentConfig, AppConfig, ModelConfig, PluginsConfig, ReplicaConfig, SkillsConfig, ToolsConfig
from moio_runtime.standalone_backend import StandaloneAgentBackend


class StandaloneBackendQueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.actor = {
            "id": 5,
            "email": "owner@example.test",
            "displayName": "Owner",
            "tenantRole": "admin",
            "tenantAdmin": True,
        }

    def _make_backend(self) -> StandaloneAgentBackend:
        cfg = ReplicaConfig(
            model=ModelConfig(api_key="test-key"),
            skills=SkillsConfig(),
            tools=ToolsConfig(
                allowlist=["files.read"],
                workspace_root=self.root,
                vendors_file=self.root / "vendors" / "vendors.json",
                shell_enabled=False,
                docker_enabled=False,
                dynamic_tools_enabled=False,
                package_install_enabled=False,
                vault_enabled=False,
            ),
            plugins=PluginsConfig(),
            agent=AgentConfig(context_compaction_enabled=False),
            app=AppConfig(),
            sessions_dir=self.root / "sessions",
        )
        return StandaloneAgentBackend(cfg, tenant_schema="tenant_a", workspace_slug="shared")

    async def test_second_turn_is_queued_until_active_run_finishes(self) -> None:
        backend = self._make_backend()
        blocker = asyncio.Event()

        async def _blocked_execute_run(**kwargs):  # pragma: no cover - exercised via backend
            _ = kwargs
            await blocker.wait()

        backend._execute_run = _blocked_execute_run  # type: ignore[method-assign]

        first = await backend.start_run(
            session_key="main",
            message="first",
            thinking="default",
            verbosity="minimal",
            model_overrides=None,
            tool_allowlist=None,
            timeout_ms=1000,
            idempotency_key="run-1",
            initiator=self.actor,
            selected_profile=None,
        )
        second = await backend.start_run(
            session_key="main",
            message="second",
            thinking="default",
            verbosity="minimal",
            model_overrides=None,
            tool_allowlist=None,
            timeout_ms=1000,
            idempotency_key="run-2",
            initiator=self.actor,
            selected_profile=None,
        )

        self.assertEqual((first.get("payload") or {}).get("status"), "started")
        self.assertEqual((second.get("payload") or {}).get("status"), "queued")
        self.assertEqual(((second.get("payload") or {}).get("queue") or {}).get("payload", {}).get("count"), 1)

        retired = await backend.retire_queued_turn(
            session_key="main",
            queue_item_id="run-2",
            initiator=self.actor,
        )
        self.assertEqual(((retired.get("payload") or {}).get("count")), 0)

        blocker.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    async def test_private_queue_force_push_reorders_items(self) -> None:
        backend = self._make_backend()
        await backend.chat_session_create("private-notes", scope="private", initiator=self.actor)
        await backend._session_save_queue(
            "private-notes",
            [
                {"id": "run-a", "message": "first", "author": self.actor, "initiator": self.actor},
                {"id": "run-b", "message": "second", "author": self.actor, "initiator": self.actor},
            ],
        )

        result = await backend.force_push_queued_turn(
            session_key="private-notes",
            queue_item_id="run-b",
            initiator=self.actor,
        )

        items = (((result.get("payload") or {}).get("items")) or [])
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].get("id"), "run-b")

    async def test_chat_session_set_scope_promotes_private_to_shared(self) -> None:
        backend = self._make_backend()
        await backend.chat_session_create("private-notes", scope="private", initiator=self.actor)

        result = await backend.chat_session_set_scope(
            session_key="private-notes",
            scope="shared",
            initiator=self.actor,
        )

        session = ((result.get("payload") or {}).get("session") or {})
        self.assertEqual(session.get("scope"), "shared")
        listed = await backend.chat_sessions_list(limit=100, initiator={"id": 8, "email": "other@example.test"})
        sessions = (((listed.get("payload") or {}).get("sessions")) or [])
        self.assertTrue(any(str(row.get("sessionKey")) == "private-notes" for row in sessions))


if __name__ == "__main__":
    unittest.main()
