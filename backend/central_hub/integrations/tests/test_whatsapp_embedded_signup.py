import pytest
from rest_framework.test import APIClient

from central_hub.models import (
    Tenant,
    MoioUser,
    PlatformConfiguration,
    TenantConfiguration,
)
from central_hub.integrations.models import IntegrationConfig


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if 400 <= self.status_code:
            import requests
            raise requests.HTTPError(f"status={self.status_code}")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def tenant():
    return Tenant.objects.create(nombre="Acme", domain="acme.com")


@pytest.fixture
def user(tenant):
    return MoioUser.objects.create_user(
        email="user@acme.com",
        username="user",
        password="pass",
        tenant=tenant,
    )


@pytest.fixture
def portal_config():
    return PlatformConfiguration.objects.create(
        my_url="https://example.com/",
        fb_moio_bot_app_id="app123",
        fb_moio_bot_app_secret="secret123",
        fb_moio_bot_configuration_id="config123",
        fb_system_token="system-token",
    )


@pytest.fixture
def tenant_config(tenant):
    return TenantConfiguration.objects.create(tenant=tenant)


def test_complete_signup_creates_integration_config(monkeypatch, api_client, user, portal_config, tenant_config):
    def fake_get(url, params=None, **kwargs):
        if "oauth/access_token" in url:
            return _FakeResponse(200, {"access_token": "abc123", "token_type": "bearer", "expires_in": 500})
        raise AssertionError(f"Unexpected GET url {url}")

    def fake_post(url, json=None, **kwargs):
        if url.endswith("/subscribed_apps"):
            return _FakeResponse(200, {"success": True})
        if url.endswith("/register"):
            return _FakeResponse(200, {"success": True})
        raise AssertionError(f"Unexpected POST url {url}")

    monkeypatch.setattr("central_hub.integrations.views.requests.get", fake_get)
    monkeypatch.setattr("central_hub.integrations.views.requests.post", fake_post)

    api_client.force_authenticate(user=user)
    payload = {
        "code": "the-code",
        "phone_number_id": "12345",
        "waba_id": "waba-1",
        "instance_name": "Support Line",
        "set_as_default": True,
    }
    resp = api_client.post(
        "/api/v1/integrations/whatsapp/embedded-signup/complete/",
        data=payload,
        format="json",
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    cfg = IntegrationConfig.objects.get(tenant=user.tenant, slug="whatsapp", instance_id="12345")
    assert cfg.enabled
    assert cfg.config["token"] == "abc123"
    assert cfg.config["phone_id"] == "12345"
    assert cfg.config["business_account_id"] == "waba-1"

    tenant_config.refresh_from_db()
    assert tenant_config.whatsapp_token == "abc123"
    assert tenant_config.whatsapp_business_account_id == "waba-1"
    assert tenant_config.whatsapp_phone_id == "12345"


def test_complete_signup_requires_fields(api_client, user, portal_config):
    api_client.force_authenticate(user=user)
    resp = api_client.post(
        "/api/v1/integrations/whatsapp/embedded-signup/complete/",
        data={"code": "missing-fields"},
        format="json",
    )
    assert resp.status_code == 400
    assert "error" in resp.json()

