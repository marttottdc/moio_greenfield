import uuid

import pytest
from django.core.exceptions import ValidationError

from flows.models import FlowScriptLog, FlowScriptRun
from flows.scripts import FlowScriptSerializer
from portal.models import Tenant


def test_flow_script_latest_and_published(flow_script_factory, flow_script_version_factory):
    script = flow_script_factory()
    v1 = flow_script_version_factory(script=script, version_number=1)
    v2 = flow_script_version_factory(script=script, version_number=2)

    assert script.latest_version.id == v2.id
    assert script.published_version is None

    v1.publish()
    script.refresh_from_db()
    assert script.published_version.id == v1.id

    v2.publish()
    script.refresh_from_db()
    assert script.published_version.id == v2.id
    v1.refresh_from_db()
    assert not v1.is_published


def test_flow_script_version_unique(flow_script_version_factory):
    version = flow_script_version_factory(version_number=1)
    with pytest.raises(ValidationError):
        flow_script_version_factory(script=version.script, version_number=1)


def test_flow_script_run_validation(flow_script_version_factory):
    version = flow_script_version_factory()
    run = FlowScriptRun(
        tenant=version.tenant,
        flow=version.flow,
        script=version.script,
        version=version,
    )
    run.save()

    other_version = flow_script_version_factory()
    with pytest.raises(ValidationError):
        FlowScriptRun(
            tenant=version.tenant,
            flow=version.flow,
            script=version.script,
            version=other_version,
        ).save()


def test_flow_script_log_validation(flow_script_version_factory):
    version = flow_script_version_factory()
    run = FlowScriptRun.objects.create(
        tenant=version.tenant,
        flow=version.flow,
        script=version.script,
        version=version,
    )
    log = FlowScriptLog(
        tenant=version.tenant,
        run=run,
        level=FlowScriptLog.LEVEL_INFO,
        message="Executed successfully",
    )
    log.save()

    config = version.tenant.configuration.first()
    if config:
        config.whatsapp_name = f"tenant-{uuid.uuid4().hex[:8]}"
        config.save(update_fields=["whatsapp_name"])

    other_tenant = Tenant.objects.create(
        nombre="Gamma",
        domain="gamma.test",
        tenant_code=uuid.uuid4(),
    )
    other_config = other_tenant.configuration.first()
    if other_config:
        other_config.whatsapp_name = f"gamma-{uuid.uuid4().hex[:8]}"
        other_config.save(update_fields=["whatsapp_name"])
    with pytest.raises(ValidationError):
        FlowScriptLog(
            tenant=other_tenant,
            run=run,
            level=FlowScriptLog.LEVEL_INFO,
            message="Cross tenant log",
        ).save()


def test_serializer_multi_tenant_isolation(flow_factory, flow_script_factory, flow_script_version_factory):
    flow = flow_factory()
    script = flow_script_factory(flow=flow)
    flow_script_version_factory(script=script)

    config = flow.tenant.configuration.first()
    if config:
        config.whatsapp_name = f"tenant-{uuid.uuid4().hex[:8]}"
        config.save(update_fields=["whatsapp_name"])

    other_tenant = Tenant.objects.create(nombre="Beta", domain="beta.test")
    other_config = other_tenant.configuration.first()
    if other_config:
        other_config.whatsapp_name = f"beta-{uuid.uuid4().hex[:8]}"
        other_config.save(update_fields=["whatsapp_name"])
    other_flow = flow_factory(tenant=other_tenant)
    other_script = flow_script_factory(flow=other_flow, tenant=other_tenant)
    flow_script_version_factory(script=other_script)

    payload = FlowScriptSerializer.for_flow(flow)
    assert len(payload) == 1
    assert payload[0]["id"] == str(script.id)
    assert payload[0]["latest_version"]["version"] == script.latest_version.version_number
