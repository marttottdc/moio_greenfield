import pytest

from django.utils.timezone import now

from flows.models import Flow, FlowExecution, FlowVersion, FlowVersionStatus
from flows.views import _stats_for


@pytest.mark.django_db
def test_stats_for_counts_active_by_status_and_published_version(tenant, user_factory):
    user = user_factory(email="owner@example.com", username="owner", tenant=tenant)

    # Flow A: published + active => enabled
    flow_a = Flow.objects.create(tenant=tenant, name="A", description="", status="active", created_by=user)
    v_a = FlowVersion.objects.create(flow=flow_a, tenant=tenant, graph={"nodes": []}, status=FlowVersionStatus.PUBLISHED, created_by=user)
    flow_a.published_version = v_a
    flow_a.save(update_fields=["published_version"])

    # Flow B: published but inactive => not enabled
    flow_b = Flow.objects.create(tenant=tenant, name="B", description="", status="inactive", created_by=user)
    v_b = FlowVersion.objects.create(flow=flow_b, tenant=tenant, graph={"nodes": []}, status=FlowVersionStatus.PUBLISHED, created_by=user)
    flow_b.published_version = v_b
    flow_b.save(update_fields=["published_version"])

    # Flow C: draft only
    flow_c = Flow.objects.create(tenant=tenant, name="C", description="", status="inactive", created_by=user)
    FlowVersion.objects.create(flow=flow_c, tenant=tenant, graph={"nodes": []}, status=FlowVersionStatus.DRAFT, created_by=user)

    stats = _stats_for(tenant=tenant)
    assert stats["total"] == 3
    assert stats["active"] == 1
    assert stats["published"] == 2


@pytest.mark.django_db
def test_execution_count_is_flow_level_across_versions(tenant, user_factory):
    user = user_factory(email="owner2@example.com", username="owner2", tenant=tenant)
    flow = Flow.objects.create(tenant=tenant, name="Runs", description="", status="active", created_by=user)
    v1 = FlowVersion.objects.create(flow=flow, tenant=tenant, graph={"nodes": []}, status=FlowVersionStatus.PUBLISHED, created_by=user)
    flow.published_version = v1
    flow.save(update_fields=["published_version"])

    FlowExecution.objects.create(flow=flow, status="success", input_data={}, trigger_source="manual", execution_context={"version_id": str(v1.id)})
    flow.execution_count = 1
    flow.last_executed_at = now()
    flow.last_execution_status = "success"
    flow.save(update_fields=["execution_count", "last_executed_at", "last_execution_status"])

    # Change published version
    v2 = FlowVersion.objects.create(flow=flow, tenant=tenant, graph={"nodes": []}, status=FlowVersionStatus.PUBLISHED, created_by=user)
    flow.published_version = v2
    flow.save(update_fields=["published_version"])

    FlowExecution.objects.create(flow=flow, status="success", input_data={}, trigger_source="manual", execution_context={"version_id": str(v2.id)})
    flow.execution_count += 1
    flow.save(update_fields=["execution_count"])

    flow.refresh_from_db()
    assert flow.execution_count == 2


