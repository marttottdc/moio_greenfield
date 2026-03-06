from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moio_runtime.session_store import (
    SessionStore,
    build_event_log_from_messages,
    normalize_queued_turn,
    normalize_session_message,
)


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.alice = {"id": 1, "email": "alice@example.com", "displayName": "Alice"}
        self.bob = {"id": 2, "email": "bob@example.com", "displayName": "Bob"}

    def test_normalize_session_message_preserves_authorship_fields(self) -> None:
        normalized = normalize_session_message(
            {
                "role": "USER",
                "timestamp": 1000,
                "author": self.alice,
                "owner": self.alice,
                "content": [{"type": "text", "text": "Hello team"}],
            }
        )

        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual(normalized["role"], "user")
        self.assertEqual(normalized["author"]["email"], "alice@example.com")
        self.assertEqual(normalized["owner"]["displayName"], "Alice")
        self.assertEqual(normalized["contextScope"], "shared")

    def test_event_log_includes_authorship_metadata(self) -> None:
        messages = [
            {
                "role": "user",
                "contextScope": "shared",
                "author": {"id": 1, "email": "alice@example.com"},
                "timestamp": 1000,
                "content": [{"type": "text", "text": "shared"}],
            },
            {
                "role": "system",
                "contextScope": "personal",
                "owner": {"id": 2, "email": "bob@example.com"},
                "timestamp": 2000,
                "content": [{"type": "text", "text": "reply from bob"}],
            },
        ]

        event_log = build_event_log_from_messages(messages)
        self.assertEqual(len(event_log), 2)
        self.assertEqual(event_log[0]["textPreview"], "shared")
        self.assertEqual(event_log[0]["author"]["email"], "alice@example.com")
        self.assertEqual(event_log[1]["owner"]["id"], 2)

    def test_event_log_limit_keeps_most_recent_entries(self) -> None:
        messages = [
            {
                "role": "user",
                "contextScope": "shared",
                "timestamp": 1000,
                "content": [{"type": "text", "text": "first"}],
            },
            {
                "role": "system",
                "contextScope": "personal",
                "owner": {"id": 2, "email": "bob@example.com"},
                "timestamp": 2000,
                "content": [{"type": "text", "text": "second"}],
            },
            {
                "role": "assistant",
                "contextScope": "shared",
                "timestamp": 3000,
                "content": [{"type": "text", "text": "latest"}],
            },
        ]

        event_log = build_event_log_from_messages(messages, limit=1)
        self.assertEqual(len(event_log), 1)
        self.assertEqual(event_log[0]["textPreview"], "latest")
        self.assertEqual(event_log[0]["sequence"], 3)

    def test_private_sessions_are_visible_only_to_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(Path(tmpdir))
            store.create_session("private-notes", scope="private", owner=self.alice)

            alice_sessions = store.list_sessions(actor=self.alice)
            bob_sessions = store.list_sessions(actor=self.bob)
            meta = store.load_session_meta("private-notes")

        self.assertEqual(len(alice_sessions), 1)
        self.assertEqual(alice_sessions[0]["scope"], "private")
        self.assertEqual(bob_sessions, [])
        self.assertEqual(meta["scope"], "private")
        self.assertEqual((meta.get("owner") or {}).get("email"), "alice@example.com")

    def test_set_session_scope_can_promote_private_to_shared(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(Path(tmpdir))
            store.create_session("private-notes", scope="private", owner=self.alice)
            updated = store.set_session_scope("private-notes", scope="shared", owner=None)
            meta = store.load_session_meta("private-notes")
            bob_sessions = store.list_sessions(actor=self.bob)

        self.assertEqual(updated["scope"], "shared")
        self.assertEqual(meta["scope"], "shared")
        self.assertIsNone(meta.get("owner"))
        self.assertEqual(len(bob_sessions), 1)
        self.assertEqual(bob_sessions[0]["sessionKey"], "private-notes")

    def test_normalize_queued_turn_preserves_execution_initiator(self) -> None:
        normalized = normalize_queued_turn(
            {
                "id": "run-1",
                "message": "",
                "attachments": [{"name": "invoice.pdf", "type": "application/pdf", "size": 12, "data": "ZmFrZQ=="}],
                "author": self.alice,
                "initiator": {
                    **self.alice,
                    "tenantId": "tenant-1",
                    "tenantRole": "admin",
                    "tenantAdmin": True,
                },
            }
        )

        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual(normalized["attachmentsCount"], 1)
        self.assertEqual((normalized.get("initiator") or {}).get("tenantRole"), "admin")
        self.assertTrue((normalized.get("initiator") or {}).get("tenantAdmin"))

    def test_session_store_persists_queued_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(Path(tmpdir))
            store.create_session("main")
            saved = store.save_queue(
                "main",
                [
                    {
                        "id": "run-2",
                        "message": "Please review this",
                        "author": self.alice,
                        "initiator": {**self.alice, "tenantRole": "member"},
                        "attachments": [{"name": "note.txt", "type": "text/plain", "size": 4, "data": "dGVzdA=="}],
                    }
                ],
            )
            loaded = store.load_queue("main")

        self.assertEqual(len(saved), 1)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["id"], "run-2")
        self.assertEqual((loaded[0].get("initiator") or {}).get("tenantRole"), "member")


if __name__ == "__main__":
    unittest.main()
