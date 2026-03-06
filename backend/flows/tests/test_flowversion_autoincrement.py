import pytest

from flows.models import Flow, FlowVersion, FlowVersionStatus


@pytest.mark.django_db
def test_flowversion_autoincrements_with_uuid_pk(tenant, user_factory):
    user = user_factory(email="owner@example.com", username="owner", tenant=tenant)
    flow = Flow.objects.create(tenant=tenant, name="AutoInc", description="", status="inactive", created_by=user)

    v1 = FlowVersion.objects.create(flow=flow, tenant=tenant, status=FlowVersionStatus.DRAFT, graph={"nodes": []}, created_by=user)
    v2 = FlowVersion.objects.create(flow=flow, tenant=tenant, status=FlowVersionStatus.DRAFT, graph={"nodes": []}, created_by=user)

    assert v1.version == 1
    assert v2.version == 2


@pytest.mark.django_db
def test_clone_as_draft_assigns_next_version(tenant, user_factory):
    user = user_factory(email="owner2@example.com", username="owner2", tenant=tenant)
    flow = Flow.objects.create(tenant=tenant, name="Clone", description="", status="inactive", created_by=user)

    published = FlowVersion.objects.create(
        flow=flow,
        tenant=tenant,
        status=FlowVersionStatus.PUBLISHED,
        graph={"nodes": []},
        created_by=user,
    )

    draft = published.clone_as_draft(user=user)
    assert draft.version == published.version + 1
    assert draft.status == FlowVersionStatus.DRAFT


