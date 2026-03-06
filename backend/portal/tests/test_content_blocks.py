from django.test import TestCase
from django.urls import reverse

from portal.content_blocks import render_blocks
from portal.context_utils import current_tenant
from portal.models import ComponentTemplate, ContentBlock, Tenant


class ContentBlocksTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nombre='Tenant', enabled=True, domain='tenant.example')
        self.token = current_tenant.set(self.tenant)
        self.addCleanup(lambda: current_tenant.reset(self.token))

        self.component = ComponentTemplate.objects.create(
            tenant=self.tenant,
            name='Hero',
            slug='hero',
            template_path='portal/partials/test_block.html',
            context_schema={
                'type': 'object',
                'properties': {
                    'title': {'type': 'string'},
                },
            },
        )

    def test_render_blocks_returns_html_in_order(self):
        ContentBlock.objects.create(
            tenant=self.tenant,
            component=self.component,
            group='home',
            title='First',
            order=2,
            context={'title': 'Second block'},
        )
        ContentBlock.objects.create(
            tenant=self.tenant,
            component=self.component,
            group='home',
            title='Second',
            order=1,
            context={'title': 'First block'},
        )

        rendered = render_blocks('home')
        self.assertIn('First block', rendered)
        self.assertIn('Second block', rendered)
        self.assertIn('portal-block--tenant_only', rendered)
        self.assertLess(rendered.index('First block'), rendered.index('Second block'))

    def test_render_blocks_exposes_block_metadata(self):
        ContentBlock.objects.create(
            tenant=self.tenant,
            component=self.component,
            group='metadata',
            title='Metadata Block',
            order=1,
            context={},
        )

        rendered = render_blocks('metadata')
        self.assertIn('Metadata Block', rendered)
        self.assertIn('portal-block--tenant_only', rendered)

    def test_render_blocks_skips_inactive(self):
        ContentBlock.objects.create(
            tenant=self.tenant,
            component=self.component,
            group='home',
            title='Active',
            order=1,
            context={'title': 'Active block'},
        )
        ContentBlock.objects.create(
            tenant=self.tenant,
            component=self.component,
            group='home',
            title='Inactive',
            order=2,
            is_active=False,
            context={'title': 'Inactive block'},
        )

        rendered = render_blocks('home')
        self.assertIn('Active block', rendered)
        self.assertNotIn('Inactive block', rendered)

    def test_view_returns_html_response(self):
        ContentBlock.objects.create(
            tenant=self.tenant,
            component=self.component,
            group='marketing',
            title='Visible',
            order=1,
            context={'title': 'Marketing block'},
        )

        url = reverse('portal_blocks', args=['marketing'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Marketing block', response.content.decode())

    def test_view_sets_hx_trigger_header(self):
        ContentBlock.objects.create(
            tenant=self.tenant,
            component=self.component,
            group='hx',
            title='HX',
            order=1,
            context={'title': 'HX block'},
        )

        url = reverse('portal_blocks', args=['hx'])
        response = self.client.get(url, HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Trigger'], '{"contentBlocksRendered": "hx"}')

    def test_view_raises_404_when_no_blocks(self):
        url = reverse('portal_blocks', args=['missing'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_public_blocks_render_without_tenant(self):
        anonymous_token = current_tenant.set(None)
        self.addCleanup(lambda: current_tenant.reset(anonymous_token))

        ContentBlock.objects.create(
            tenant=self.tenant,
            component=self.component,
            group='public',
            title='Public',
            order=1,
            visibility=ContentBlock.Visibility.PUBLIC,
            context={'title': 'Public block'},
        )
        ContentBlock.objects.create(
            tenant=self.tenant,
            component=self.component,
            group='public',
            title='Private',
            order=2,
            visibility=ContentBlock.Visibility.TENANT_ONLY,
            context={'title': 'Private block'},
        )

        rendered = render_blocks('public')
        self.assertIn('Public block', rendered)
        self.assertNotIn('Private block', rendered)
        self.assertIn('portal-block--public', rendered)
        self.assertNotIn('portal-block--tenant_only', rendered)

    def test_private_blocks_hidden_from_other_tenants(self):
        other_tenant = Tenant.objects.create(nombre='Other', enabled=True, domain='other.example')
        other_token = current_tenant.set(other_tenant)
        self.addCleanup(lambda: current_tenant.reset(other_token))

        ContentBlock.objects.create(
            tenant=self.tenant,
            component=self.component,
            group='home',
            title='Private',
            order=1,
            visibility=ContentBlock.Visibility.TENANT_ONLY,
            context={'title': 'Private block'},
        )
        ContentBlock.objects.create(
            tenant=self.tenant,
            component=self.component,
            group='home',
            title='Public',
            order=2,
            visibility=ContentBlock.Visibility.PUBLIC,
            context={'title': 'Public block'},
        )

        rendered = render_blocks('home')
        self.assertNotIn('Private block', rendered)
        self.assertIn('Public block', rendered)
