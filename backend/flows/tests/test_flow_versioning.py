import pytest

from flows.models import FlowVersion, FlowVersionStatus


@pytest.mark.django_db
def test_publish_demotes_other_testing_versions(flow_factory, tenant, user_factory):
    user = user_factory(email="owner@example.com", username="owner", tenant=tenant)
    flow = flow_factory(tenant=tenant, created_by=user)

    v1 = FlowVersion.objects.create(flow=flow, tenant=tenant, graph={"nodes": []}, created_by=user)
    v2 = FlowVersion.objects.create(flow=flow, tenant=tenant, graph={"nodes": []}, created_by=user)

    # Put v1 into testing.
    v1.start_testing()
    v1.save()
    assert FlowVersion.objects.filter(flow=flow, status=FlowVersionStatus.TESTING).count() == 1

    # Publish v2; v1 must be demoted back to draft.
    v2.publish()
    v2.save()

    assert FlowVersion.objects.filter(flow=flow, status=FlowVersionStatus.TESTING).count() == 0
    assert FlowVersion.objects.get(id=v1.id).status == FlowVersionStatus.DRAFT
    assert FlowVersion.objects.get(id=v2.id).status == FlowVersionStatus.PUBLISHED


