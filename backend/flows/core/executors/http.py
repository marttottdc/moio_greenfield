"""
HTTP Executors - HTTP Request Celery Task

Standalone Celery task for making HTTP requests that can be:
1. Called directly from anywhere (webhooks, views, scripts)
2. Registered as flow node executors

Returns structured ExecutorResult for downstream chaining.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from celery import shared_task

from moio_platform.settings import FLOWS_Q

from .base import (
    ExecutorResult,
    ExecutorContext,
    create_result,
    log_entry,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="executors.http_request", queue=FLOWS_Q)
def http_request_task(
    self,
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    auth: Optional[Dict[str, str]] = None,
    verify_ssl: bool = True,
    sandbox: bool = False,
) -> Dict[str, Any]:
    """
    Make an HTTP request to an external API.
    
    Args:
        url: The URL to request
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        headers: Optional HTTP headers
        body: Optional request body (for POST/PUT/PATCH)
        timeout: Request timeout in seconds (default 30)
        auth: Optional auth dict with 'type' ('basic' or 'bearer') and credentials
        verify_ssl: Whether to verify SSL certificates (default True)
        sandbox: If True, skip actual request and return simulated result
    
    Returns:
        ExecutorResult dict with:
        - success: bool
        - data: {status_code, response_data, response_headers, ...}
        - logs: execution logs
        - error: error message if failed
        - metadata: timing info
    """
    with ExecutorContext("http_request", self.request.id, sandbox=sandbox) as ctx:
        result = ctx.result
        
        if ctx.sandbox:
            return ctx.sandbox_skip(
                f"HTTP {method} request to {url}",
                {
                    "status_code": 200,
                    "response_data": {"sandbox": True, "message": "Simulated response"},
                    "response_headers": {"X-Sandbox": "true"},
                    "url": url,
                    "method": method,
                }
            )
        
        result.info(f"Making {method} request to {url}")
        
        try:
            import requests
            from requests.auth import HTTPBasicAuth
        except ImportError as e:
            result.success = False
            result.error = f"Requests library not available: {e}"
            result.error_log(result.error)
            return result.to_dict()
        
        try:
            request_headers = headers or {}
            request_kwargs: Dict[str, Any] = {
                "url": url,
                "method": method.upper(),
                "headers": request_headers,
                "timeout": timeout,
                "verify": verify_ssl,
            }
            
            if body and method.upper() in ("POST", "PUT", "PATCH"):
                if "Content-Type" not in request_headers:
                    request_headers["Content-Type"] = "application/json"
                
                if request_headers.get("Content-Type") == "application/json":
                    request_kwargs["json"] = body
                else:
                    request_kwargs["data"] = body
            
            if auth:
                auth_type = auth.get("type", "").lower()
                if auth_type == "basic":
                    request_kwargs["auth"] = HTTPBasicAuth(
                        auth.get("username", ""),
                        auth.get("password", "")
                    )
                elif auth_type == "bearer":
                    token = auth.get("token", "")
                    request_headers["Authorization"] = f"Bearer {token}"
            
            response = requests.request(**request_kwargs)
            
            try:
                response_data = response.json()
            except Exception:
                response_data = response.text
            
            result.data = {
                "status_code": response.status_code,
                "response_data": response_data,
                "response_headers": dict(response.headers),
                "url": url,
                "method": method,
            }
            
            if response.ok:
                result.success = True
                result.info(f"Request successful: {response.status_code}")
            else:
                result.success = False
                result.error = f"Request failed with status {response.status_code}"
                result.warning(f"Request failed: {response.status_code}", {"response": str(response_data)[:500]})
                
        except requests.exceptions.Timeout:
            result.success = False
            result.error = f"Request timed out after {timeout} seconds"
            result.error_log(result.error)
        except requests.exceptions.ConnectionError as e:
            result.success = False
            result.error = f"Connection error: {e}"
            result.error_log(result.error)
        except Exception as e:
            result.success = False
            result.error = f"HTTP request failed: {e}"
            result.error_log(result.error)
    
    return ctx.result.to_dict()


def http_request_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for HTTP requests."""
    task_kwargs = {
        "url": config.get("url") or payload.get("url", ""),
        "method": config.get("method", "GET"),
        "headers": config.get("headers"),
        "body": config.get("body"),
        "timeout": config.get("timeout", 30),
        "auth": config.get("auth"),
        "verify_ssl": config.get("verify_ssl", True),
    }
    
    if config.get("async", False):
        task = http_request_task.apply_async(kwargs=task_kwargs)  # type: ignore[attr-defined]
        return create_result(
            success=True,
            data={"task_id": task.id, "status": "queued"},
            logs=[log_entry("INFO", f"HTTP request task queued: {task.id}")],
        )
    else:
        return http_request_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]
