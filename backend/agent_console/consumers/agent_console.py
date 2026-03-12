"""
WebSocket consumer for the agent console (agent_console.runtime AgentConsoleBackend).

Protocol: client connects with ?accessToken=JWT&workspace=main; server sends "init" frame
with authUser, agentConfig, chatHistory, chatQueue, chatUsage, chatSummary, chatSessions, resources.
Client sends { action, sessionKey, message, ... }; server responds with type/payload frames.
Runtime events (chat_event, agent_event, chat_queue) are forwarded via set_event_sink.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError

from agent_console.services.runtime_service import (
    OpenAINotConfiguredError,
    TenantRequiredError,
    get_runtime_backend_for_user,
    runtime_initiator_from_user as _runtime_initiator_from_user,
)

logger = logging.getLogger(__name__)


class AgentConsoleConsumer(AsyncJsonWebsocketConsumer):
    """Speaks the agent-console protocol; bridges to AgentConsoleBackend."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self._initiator = None
        self._backend = None
        self._session_key = "main"
        self._workspace_slug = "main"
        self._auth_expiry_task: asyncio.Task | None = None
        self._token_exp_ts: int | None = None

    async def connect(self):
        query_string = (self.scope.get("query_string") or b"").decode()
        params = {}
        for part in query_string.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k.strip()] = v.strip()

        token = params.get("accessToken") or params.get("token")
        if not token:
            await self.close(code=4001)
            return

        try:
            access_token = AccessToken(token)
            user_id = access_token.get("user_id")
            if not user_id:
                await self.close(code=4001)
                return
            exp_raw = access_token.get("exp")
            self._token_exp_ts = int(exp_raw) if exp_raw is not None else None
        except TokenError:
            await self.close(code=4001)
            return

        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            self.user = await asyncio.to_thread(
                lambda: User.objects.select_related("tenant").get(pk=user_id)
            )
        except User.DoesNotExist:
            await self.close(code=4001)
            return

        if getattr(self.user, "tenant_id", None) in (None, ""):
            await self.accept()
            await self.send_json(
                {
                    "type": "error",
                    "payload": {
                        "message": TenantRequiredError.MESSAGE,
                        "code": "tenant_required",
                    },
                }
            )
            await self.close(code=4403)
            return

        self._initiator = _build_initiator(self.user, access_token=token)
        self._workspace_slug = (params.get("workspace") or "main").strip().lower() or "main"
        self._session_key = (params.get("sessionKey") or self._workspace_slug or "main").strip().lower() or "main"

        try:
            self._backend = await asyncio.to_thread(
                get_runtime_backend_for_user,
                self.user,
                workspace_slug=self._workspace_slug,
            )
        except OpenAINotConfiguredError as e:
            logger.warning("Agent console rejected: %s", e)
            await self.accept()
            await self.send_json({
                "type": "error",
                "payload": {"message": str(e), "code": "openai_not_configured"},
            })
            await self.close(code=4500)
            return
        except TenantRequiredError as e:
            logger.warning("Agent console rejected: %s", e)
            await self.accept()
            await self.send_json(
                {
                    "type": "error",
                    "payload": {"message": str(e), "code": "tenant_required"},
                }
            )
            await self.close(code=4403)
            return
        except Exception as e:
            logger.exception("Failed to get runtime backend for user")
            await self.accept()
            await self.send_json({
                "type": "error",
                "payload": {"message": str(e), "code": "backend_error"},
            })
            await self.close(code=4500)
            return

        async def _event_sink(frame: Dict[str, Any]) -> None:
            await self._send_frame(frame)

        self._backend.set_event_sink(_event_sink)

        await self.accept()
        self._schedule_auth_expiry_timer()

        try:
            init_payload = await self._build_init_payload()
            await self._send_frame({"type": "init", "payload": init_payload})
        except Exception as e:
            logger.exception("Failed to send init: %s", e)
            await self._send_frame({
                "type": "error",
                "payload": {"message": str(e), "code": "init_failed"},
            })

    async def _send_frame(self, frame: Dict[str, Any]):
        await self.send_json(frame)

    async def _build_init_payload(self) -> Dict[str, Any]:
        initiator = self._initiator
        session_key = self._session_key
        backend = self._backend

        agent_runtime = await backend.agent_runtime(initiator=initiator)
        active = (
            dict(agent_runtime.get("activeProfile", {}))
            if isinstance(agent_runtime.get("activeProfile"), dict)
            else {}
        )
        agent_config = {
            "tenant": backend.tenant_schema or (initiator.get("tenantId") or ""),
            "workspace": self._workspace_slug,
            "sessionKey": session_key,
            "model": str(active.get("model") or getattr(backend.config.model, "model", "gpt-4.1-mini") or "gpt-4.1-mini"),
            "vendor": str(active.get("vendor") or getattr(backend.config.model, "provider", "openai") or "openai"),
            "thinking": str(active.get("thinking") or getattr(backend.config.agent, "thinking", "default") or "default"),
            "verbosity": str(active.get("verbosity") or getattr(backend.config.agent, "verbosity", "minimal") or "minimal"),
        }

        chat_history = await backend.chat_history(session_key, initiator=initiator)
        chat_queue = await backend.chat_queue(session_key, initiator=initiator)
        chat_usage = await backend.chat_usage(session_key, initiator=initiator)
        chat_summary = await backend.chat_summary(session_key, initiator=initiator)
        chat_sessions = await backend.chat_sessions_list(limit=300, initiator=initiator)
        resources = await backend.resources(initiator=initiator)

        return {
            "authUser": initiator,
            "agentConfig": agent_config,
            "chatHistory": chat_history,
            "chatQueue": chat_queue,
            "chatUsage": chat_usage,
            "chatSummary": chat_summary,
            "chatSessions": chat_sessions,
            "resources": resources,
        }

    async def disconnect(self, close_code):
        if self._auth_expiry_task is not None:
            self._auth_expiry_task.cancel()
            self._auth_expiry_task = None
        if self._backend is not None:
            self._backend.set_event_sink(None)
        await super().disconnect(close_code)

    def _schedule_auth_expiry_timer(self) -> None:
        if self._auth_expiry_task is not None:
            self._auth_expiry_task.cancel()
            self._auth_expiry_task = None
        if not self._token_exp_ts:
            return
        self._auth_expiry_task = asyncio.create_task(self._auth_expiry_watchdog(self._token_exp_ts))

    async def _auth_expiry_watchdog(self, exp_ts: int) -> None:
        try:
            now = time.time()
            warn_seconds = 60
            warn_delay = max(0.0, float(exp_ts) - now - warn_seconds)
            if warn_delay > 0:
                await asyncio.sleep(warn_delay)
            seconds_left = max(0, int(float(exp_ts) - time.time()))
            await self._send_frame(
                {
                    "type": "auth_expiring",
                    "payload": {
                        "expiresIn": seconds_left,
                        "expiresAt": int(exp_ts),
                        "code": "auth_expiring",
                    },
                }
            )
            close_delay = max(0.0, float(exp_ts) - time.time())
            if close_delay > 0:
                await asyncio.sleep(close_delay)
            await self.close(code=4401)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Agent console auth expiry watchdog failed")

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        data = {k: v for k, v in content.items() if k != "action"}
        await self._on_message(action, data)

    async def _on_message(self, action: str, data: Dict[str, Any]):
        if not self._backend or not self._initiator:
            await self._send_frame({"type": "error", "payload": {"message": "Not initialized", "code": "not_ready"}})
            return

        session_key = (data.get("sessionKey") or self._session_key or "main").strip().lower() or "main"
        initiator = self._initiator

        try:
            if action == "init":
                init_payload = await self._build_init_payload()
                await self._send_frame({"type": "init", "payload": init_payload})
                return

            if action == "send_message":
                message = (data.get("message") or "").strip()
                attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else None
                thinking = data.get("thinking")
                verbosity = data.get("verbosity")
                model_overrides = data.get("modelOverrides") if isinstance(data.get("modelOverrides"), dict) else None
                tool_allowlist = data.get("toolAllowlist") if isinstance(data.get("toolAllowlist"), list) else None
                timeout_ms = data.get("timeoutMs") if isinstance(data.get("timeoutMs"), (int, float)) else None
                idempotency_key = (data.get("idempotencyKey") or data.get("runId") or "").strip() or None
                selected_profile = (data.get("selectedProfile") or "").strip() or None

                result = await self._backend.start_run(
                    session_key=session_key,
                    message=message or "Please analyze attached files.",
                    attachments=attachments,
                    thinking=thinking,
                    verbosity=verbosity,
                    model_overrides=model_overrides,
                    tool_allowlist=tool_allowlist,
                    timeout_ms=int(timeout_ms) if timeout_ms else None,
                    idempotency_key=idempotency_key,
                    initiator=initiator,
                    selected_profile=selected_profile,
                )
                payload = result.get("payload") if isinstance(result.get("payload"), dict) else result
                await self._send_frame({
                    "type": "chat_send_ack",
                    "payload": {
                        "result": {
                            "payload": payload,
                            "ok": result.get("ok", True),
                        },
                    },
                })
                return

            if action == "chat_history":
                out = await self._backend.chat_history(session_key, initiator=initiator)
                await self._send_frame({"type": "chat_history", "payload": out})
                return

            if action == "chat_queue":
                out = await self._backend.chat_queue(session_key, initiator=initiator)
                await self._send_frame({"type": "chat_queue", "payload": out})
                return

            if action == "chat_summary":
                out = await self._backend.chat_summary(session_key, initiator=initiator)
                await self._send_frame({"type": "chat_summary", "payload": out})
                return

            if action == "chat_usage":
                out = await self._backend.chat_usage(session_key, initiator=initiator)
                await self._send_frame({"type": "chat_usage", "payload": out})
                return

            if action == "chat_sessions_list":
                limit = int(data.get("limit", 200))
                out = await self._backend.chat_sessions_list(limit=limit, initiator=initiator)
                await self._send_frame({"type": "chat_sessions_list", "payload": out})
                return

            if action == "chat_session_create":
                key = (data.get("sessionKey") or data.get("key") or "").strip()
                scope = (data.get("scope") or "shared").strip().lower() or "shared"
                out = await self._backend.chat_session_create(key or None, scope=scope, initiator=initiator)
                await self._send_frame({"type": "chat_session_create", "payload": out})
                return

            if action == "chat_session_set_scope":
                scope = (data.get("scope") or "shared").strip().lower() or "shared"
                out = await self._backend.chat_session_set_scope(
                    session_key=session_key, scope=scope, initiator=initiator
                )
                await self._send_frame({"type": "chat_session_set_scope", "payload": out})
                return

            if action == "chat_session_rename":
                title = (data.get("title") or "").strip()
                out = await self._backend.chat_session_rename(
                    session_key=session_key, title=title, initiator=initiator
                )
                await self._send_frame({"type": "chat_session_rename", "payload": out})
                return

            if action == "chat_queue_retire":
                queue_item_id = (data.get("queueItemId") or "").strip()
                if queue_item_id:
                    out = await self._backend.retire_queued_turn(
                        session_key=session_key, queue_item_id=queue_item_id, initiator=initiator
                    )
                else:
                    out = await self._backend.chat_queue(session_key, initiator=initiator)
                await self._send_frame({"type": "chat_queue_retire", "payload": out})
                return

            if action == "chat_queue_force_push":
                queue_item_id = (data.get("queueItemId") or "").strip()
                if queue_item_id:
                    out = await self._backend.force_push_queued_turn(
                        session_key=session_key, queue_item_id=queue_item_id, initiator=initiator
                    )
                else:
                    out = await self._backend.chat_queue(session_key, initiator=initiator)
                await self._send_frame({"type": "chat_queue_force_push", "payload": out})
                return

            if action == "abort":
                run_id = (data.get("runId") or "").strip() or None
                await self._backend.abort(
                    session_key=session_key,
                    run_id=run_id,
                    initiator=initiator,
                )
                await self._send_frame({"type": "abort", "payload": {"runId": run_id}})
                return

            await self._send_frame({
                "type": "error",
                "payload": {"message": f"Unknown action: {action}", "code": "unknown_action"},
            })
        except Exception as e:
            logger.exception("Agent console action %s failed: %s", action, e)
            await self._send_frame({
                "type": "error",
                "payload": {"message": str(e), "code": "action_failed"},
            })


def _build_initiator(user, *, access_token: str | None = None) -> Dict[str, Any]:
    d = dict(_runtime_initiator_from_user(user))
    tenant_id = getattr(user, "tenant_id", None)
    if tenant_id is not None:
        d["tenantId"] = str(tenant_id or "")
    if access_token:
        d["accessToken"] = access_token
    return d
