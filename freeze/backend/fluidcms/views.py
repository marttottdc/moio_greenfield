from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers as drf_serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from portal.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from portal.models import Tenant
from security.authentication import ServiceJWTAuthentication
from security.permissions import RequireServiceScope
from . import models, serializers


def normalize_locale(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.replace('_', '-').lower()


def _resolve_blocks(
    page: models.FluidPage,
    requested_locale: Optional[str],
) -> List[Dict[str, Any]]:
    normalized_requested = normalize_locale(requested_locale) or page.default_locale
    blocks = page.blocks.filter(is_active=True).order_by('order', 'created_at').all()

    grouped: Dict[str, List[models.FluidBlock]] = defaultdict(list)
    for block in blocks:
        grouped[block.key].append(block)

    resolved_blocks: List[Dict[str, Any]] = []

    for key, block_group in grouped.items():
        block_group.sort(key=lambda b: (b.order, b.created_at))
        available_by_locale = {block.locale: block for block in block_group}

        fallback_candidates: List[str] = []
        if normalized_requested:
            fallback_candidates.append(normalized_requested)

        block_override = next((b.fallback_locale for b in block_group if b.fallback_locale), None)
        if block_override and block_override not in fallback_candidates:
            fallback_candidates.append(block_override)

        if page.default_locale and page.default_locale not in fallback_candidates:
            fallback_candidates.append(page.default_locale)

        seen: List[str] = []
        chosen_block: Optional[models.FluidBlock] = None
        resolved_locale: Optional[str] = None

        for candidate in fallback_candidates:
            if candidate in seen:
                continue
            seen.append(candidate)
            block = available_by_locale.get(candidate)
            if block:
                chosen_block = block
                resolved_locale = block.locale
                break

        if chosen_block is None:
            chosen_block = block_group[0]
            resolved_locale = chosen_block.locale
            if resolved_locale not in seen:
                seen.append(resolved_locale)

        fallback_applied = resolved_locale != normalized_requested

        # Extract content from config (content is what frontend sends/expects)
        config = chosen_block.config or {}
        content = {k: v for k, v in config.items() if k != 'styling'}
        styling = config.get('styling', {})

        block_data = {
            'key': key,
            'type': chosen_block.type,
            'layout': chosen_block.layout,
            'content': content,
            'order': chosen_block.order,
            'isActive': chosen_block.is_active,
            'locale': {
                'requested': normalized_requested,
                'resolved': resolved_locale,
                'fallbackApplied': fallback_applied,
                'fallbackChain': seen,
            },
        }

        # Add styling if present
        if styling:
            block_data['styling'] = styling

        resolved_blocks.append(block_data)

    resolved_blocks.sort(key=lambda block: (block['order'], block['key']))
    return resolved_blocks


def _assemble_page_payload(
    page: models.FluidPage, requested_locale: Optional[str]
) -> Dict[str, Any]:
    normalized_requested = normalize_locale(requested_locale) or page.default_locale
    blocks = _resolve_blocks(page, normalized_requested)

    fallback_applied = any(block['locale']['fallbackApplied'] for block in blocks)
    resolved_candidates = [block['locale']['resolved'] for block in blocks if block['locale']['resolved']]
    resolved_locale = (
        resolved_candidates[0]
        if resolved_candidates
        else (normalized_requested or page.default_locale)
    )

    # Extract layout-related fields from metadata
    metadata = page.metadata or {}
    layout_obj = {
        'themeId': metadata.get('themeId', ''),
        'fontCombinationId': metadata.get('fontCombinationId', ''),
        'siteInfo': metadata.get('siteInfo', {}),
    }

    # Include any additional layout properties stored in metadata
    if 'layout' in metadata:
        layout_obj.update(metadata['layout'])

    response_data = {
        'id': str(page.id),
        'slug': page.slug,
        'name': page.name,
        'description': page.description,
        'layout': layout_obj,
        'status': page.status,
        'isActive': page.is_active,
        'isHome': page.is_home,
        'locale': {
            'requested': normalized_requested,
            'default': page.default_locale,
            'resolved': resolved_locale,
            'fallbackApplied': fallback_applied,
        },
        'blocks': blocks,
    }

    return response_data


class AuthenticatedAPIView(APIView):
    """
    Base API view for FluidCMS endpoints requiring user authentication.
    Uses standard JWT auth for CMS management operations.
    """
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated]


class ContentPageView(AuthenticatedAPIView):
    """Authenticated endpoint for fetching and updating content pages. Requires user JWT authentication."""
    CACHE_CONTROL_HEADER = 'public, max-age=300'
    VARY_HEADER = 'Accept-Language'

    @extend_schema(
        tags=['FluidCMS'],
        summary='Fetch content page',
        description='Returns a fully resolved content page with blocks for the requested page ID. Requires authentication.',
        parameters=[
            OpenApiParameter('locale', OpenApiTypes.STR, OpenApiParameter.QUERY, description='Preferred locale code'),
        ],
        responses={
            200: inline_serializer(
                name='ContentPageResponse',
                fields={
                    'id': drf_serializers.UUIDField(),
                    'slug': drf_serializers.CharField(),
                    'page': drf_serializers.JSONField(),
                },
            ),
            404: OpenApiResponse(description='Page not found'),
        },
    )
    def get(self, request, page_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')
        
        locale = request.query_params.get('locale') or request.headers.get('Accept-Language')
        page = get_object_or_404(
            models.FluidPage.objects.filter(tenant=tenant, is_active=True),
            id=page_id,
        )
        payload = _assemble_page_payload(page, locale)
        payload['id'] = str(page.id)
        response = Response(payload)
        response['Cache-Control'] = self.CACHE_CONTROL_HEADER
        response['Vary'] = self.VARY_HEADER
        return response

    @extend_schema(
        tags=['FluidCMS'],
        summary='Update content page',
        description='Replaces the blocks for a content page.',
        parameters=[
            OpenApiParameter('locale', OpenApiTypes.STR, OpenApiParameter.QUERY, description='Locale to resolve'),
        ],
        request=serializers.FluidPageUpsertSerializer,
        responses={
            200: inline_serializer(
                name='ContentPageUpdateResponse',
                fields={'page': drf_serializers.JSONField()},
            ),
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def put(self, request, page_id: str):
        import logging
        from django.conf import settings
        logger = logging.getLogger(__name__)

        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        locale = request.query_params.get('locale') or request.data.get('locale')

        logger.info(f'PUT /api/v1/fluidcms/content/pages/{page_id}')

        if settings.DEBUG:
            logger.info(f'Full request data (DEBUG mode): {request.data}')

        logger.info(f'Request data keys: {list(request.data.keys())}')
        if 'blocks' in request.data:
            logger.info(f"Received {len(request.data['blocks'])} blocks in request")

        # Try to get existing page by ID
        try:
            page = models.FluidPage.objects.get(tenant=tenant, id=page_id)
            logger.info(f'Updating existing page: {page.slug} (id={page.id}), current blocks: {page.blocks.count()}')
        except models.FluidPage.DoesNotExist:
            raise ValidationError(f'Page with id {page_id} not found')

        serializer = serializers.FluidPageUpsertSerializer(
            page, data=request.data, context={'tenant': tenant}
        )
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            page = serializer.save()
            logger.info(f'After save - Page: {page.slug}, blocks count: {page.blocks.count()}')

        page.refresh_from_db()
        payload = _assemble_page_payload(page, locale)
        logger.info(f"Response payload - blocks count: {len(payload.get('blocks', []))}")

        return Response(payload, status=status.HTTP_200_OK)


class ContentPageCreateView(AuthenticatedAPIView):
    @extend_schema(
        tags=['FluidCMS'],
        summary='Create content page',
        description='Creates a new content page with nested blocks.',
        parameters=[
            OpenApiParameter('locale', OpenApiTypes.STR, OpenApiParameter.QUERY, description='Locale to resolve'),
        ],
        request=serializers.FluidPageUpsertSerializer,
        responses={
            201: inline_serializer(
                name='ContentPageCreateResponse',
                fields={'page': drf_serializers.JSONField()},
            ),
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        import logging
        from django.conf import settings
        logger = logging.getLogger(__name__)

        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        logger.info('POST /api/v1/fluidcms/content/pages')

        if settings.DEBUG:
            logger.info(f'Full request data (DEBUG mode): {request.data}')

        logger.info(f'Request data keys: {list(request.data.keys())}')
        if 'blocks' in request.data:
            logger.info(f"Received {len(request.data['blocks'])} blocks in request")

        serializer = serializers.FluidPageUpsertSerializer(
            data=request.data, context={'tenant': tenant}
        )

        if not serializer.is_valid():
            logger.error(f'Validation errors: {serializer.errors}')

        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            page = serializer.save()

        locale = request.query_params.get('locale') or request.data.get('locale')
        payload = _assemble_page_payload(page, locale)
        return Response(payload, status=status.HTTP_201_CREATED)


class ContentSitemapView(AuthenticatedAPIView):
    """Authenticated endpoint for fetching the content sitemap. Requires user JWT."""
    CACHE_CONTROL_HEADER = 'public, max-age=300'
    VARY_HEADER = 'Accept-Language'

    @extend_schema(
        tags=['FluidCMS'],
        summary='List content sitemap',
        description='Returns a lightweight sitemap of pages. Requires user authentication.',
        responses={
            200: inline_serializer(
                name='ContentSitemapResponse',
                fields={'pages': drf_serializers.JSONField()},
            )
        },
    )
    def get(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')
        
        pages = (
            models.FluidPage.objects.filter(tenant=tenant, is_active=True)
            .prefetch_related('blocks')
            .order_by('slug')
        )

        sitemap: List[Dict[str, Any]] = []
        for page in pages:
            blocks = [block for block in page.blocks.all() if block.is_active]
            available_locales = sorted({block.locale for block in blocks})
            page_locale_set = set(available_locales)

            # Add fallback locales
            for block in blocks:
                if block.fallback_locale:
                    page_locale_set.add(block.fallback_locale)

            block_keys = sorted({block.key for block in blocks})

            # Extract layout-related fields from metadata for sitemap
            metadata = page.metadata or {}
            layout_obj = {
                'themeId': metadata.get('themeId', ''),
                'fontCombinationId': metadata.get('fontCombinationId', ''),
                'siteInfo': metadata.get('siteInfo', {}),
            }
            if 'layout' in metadata:
                layout_obj.update(metadata['layout'])

            sitemap.append({
                'id': str(page.id),
                'slug': page.slug,
                'name': page.name,
                'layout': layout_obj,
                'status': page.status,
                'isActive': page.is_active,
                'isHome': page.is_home,
                'defaultLocale': page.default_locale,
                'locales': sorted(page_locale_set | {page.default_locale}),
                'blockKeys': block_keys,
                'blockCount': len(blocks),
            })

        response = Response({'pages': sitemap})
        response['Cache-Control'] = self.CACHE_CONTROL_HEADER
        response['Vary'] = self.VARY_HEADER
        return response


class ContentLiveView(APIView):
    """Service endpoint for React renderer to fetch live content pages. Requires service token."""
    CACHE_CONTROL_HEADER = 'public, max-age=300'
    VARY_HEADER = 'Accept-Language'
    authentication_classes = [ServiceJWTAuthentication]
    permission_classes = [RequireServiceScope]
    required_scope = "pages.read"

    @extend_schema(
        tags=['FluidCMS'],
        summary='Fetch live content page',
        description='Returns a fully resolved content page with blocks for the requested page ID. Requires service token authentication.',
        parameters=[
            OpenApiParameter('locale', OpenApiTypes.STR, OpenApiParameter.QUERY, description='Preferred locale code'),
        ],
        responses={
            200: inline_serializer(
                name='ContentLivePageResponse',
                fields={
                    'id': drf_serializers.UUIDField(),
                    'slug': drf_serializers.CharField(),
                    'page': drf_serializers.JSONField(),
                },
            ),
            404: OpenApiResponse(description='Page not found'),
        },
    )
    def get(self, request, page_id: str):
        locale = request.query_params.get('locale') or request.headers.get('Accept-Language')
        page = get_object_or_404(
            models.FluidPage.objects.filter(
                is_active=True,
                status__in=[models.FluidPage.PageStatus.LIVE, models.FluidPage.PageStatus.PUBLIC]
            ),
            id=page_id,
        )
        payload = _assemble_page_payload(page, locale)
        payload['id'] = str(page.id)
        response = Response(payload)
        response['Cache-Control'] = self.CACHE_CONTROL_HEADER
        response['Vary'] = self.VARY_HEADER
        return response


class TenantHomeView(APIView):
    """Service endpoint for fetching tenant home page by subdomain"""
    CACHE_CONTROL_HEADER = 'public, max-age=300'
    VARY_HEADER = 'Accept-Language'
    authentication_classes = [ServiceJWTAuthentication]
    permission_classes = [RequireServiceScope]
    required_scope = "tenant.config.read"

    @extend_schema(
        tags=['FluidCMS'],
        summary='Fetch tenant home page',
        description='Returns the home page for a tenant identified by subdomain. Only returns live/public pages.',
        parameters=[
            OpenApiParameter('locale', OpenApiTypes.STR, OpenApiParameter.QUERY, description='Preferred locale code'),
        ],
        responses={
            200: inline_serializer(
                name='TenantHomePageResponse',
                fields={
                    'id': drf_serializers.UUIDField(),
                    'slug': drf_serializers.CharField(),
                    'page': drf_serializers.JSONField(),
                },
            ),
            404: OpenApiResponse(description='Tenant or home page not found'),
        },
    )
    def get(self, request, subdomain: str):
        locale = request.query_params.get('locale') or request.headers.get('Accept-Language')
        
        # Find tenant by subdomain
        tenant = get_object_or_404(
            Tenant.objects.filter(enabled=True),
            subdomain__iexact=subdomain
        )
        
        # Find home page for tenant
        page = get_object_or_404(
            models.FluidPage.objects.filter(
                tenant=tenant,
                is_home=True,
                is_active=True,
                status__in=[models.FluidPage.PageStatus.LIVE, models.FluidPage.PageStatus.PUBLIC]
            )
        )
        
        payload = _assemble_page_payload(page, locale)
        payload['id'] = str(page.id)
        payload['tenant'] = {
            'id': tenant.id,
            'name': tenant.nombre,
            'domain': tenant.domain,
        }
        response = Response(payload)
        response['Cache-Control'] = self.CACHE_CONTROL_HEADER
        response['Vary'] = self.VARY_HEADER
        return response


class MediaView(AuthenticatedAPIView):
    """Media upload, list, and delete endpoints"""

    MIME_TYPE_MAP = {
        'image/jpeg': 'image',
        'image/png': 'image',
        'image/gif': 'image',
        'image/webp': 'image',
        'image/svg+xml': 'image',
        'video/mp4': 'video',
        'video/webm': 'video',
        'video/quicktime': 'video',
        'application/pdf': 'document',
        'application/msword': 'document',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'document',
        'text/plain': 'document',
    }

    @extend_schema(
        tags=['FluidCMS Media'],
        summary='Upload media file',
        description='Upload a media file (image, video, document). Maximum file size: 50MB.',
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'file': {'type': 'string', 'format': 'binary'},
                    'metadata': {'type': 'object'},
                },
                'required': ['file'],
            }
        },
        responses={
            201: serializers.FluidMediaSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        upload_serializer = serializers.FluidMediaUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)

        uploaded_file = upload_serializer.validated_data['file']
        metadata = upload_serializer.validated_data.get('metadata', {})

        mime_type = uploaded_file.content_type or ''
        media_type = self.MIME_TYPE_MAP.get(mime_type, 'other')

        media = models.FluidMedia(
            tenant=tenant,
            filename=uploaded_file.name,
            type=media_type,
            mime_type=mime_type,
            size=uploaded_file.size,
            metadata=metadata,
        )
        media.file.save(uploaded_file.name, uploaded_file, save=False)
        media.save()

        response_serializer = serializers.FluidMediaSerializer(media)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=['FluidCMS Media'],
        summary='List media files',
        description='List all media files for the tenant. Filter by type with ?type=image|video|document|other',
        parameters=[
            OpenApiParameter('type', OpenApiTypes.STR, OpenApiParameter.QUERY, 
                           description='Filter by media type: image, video, document, other'),
        ],
        responses={
            200: serializers.FluidMediaSerializer(many=True),
        },
    )
    def get(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        queryset = models.FluidMedia.objects.filter(tenant=tenant)

        media_type = request.query_params.get('type')
        if media_type:
            queryset = queryset.filter(type=media_type)

        serializer = serializers.FluidMediaSerializer(queryset, many=True)
        return Response(serializer.data)


class MediaDetailView(AuthenticatedAPIView):
    """Get or delete media by ID"""

    @extend_schema(
        tags=['FluidCMS Media'],
        summary='Get media file',
        description='Return a single media file by ID (same shape as list items).',
        responses={
            200: serializers.FluidMediaSerializer,
            404: OpenApiResponse(description='Media not found'),
        },
    )
    def get(self, request, media_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        media = get_object_or_404(
            models.FluidMedia.objects.filter(tenant=tenant),
            id=media_id
        )
        serializer = serializers.FluidMediaSerializer(media)
        return Response(serializer.data)

    @extend_schema(
        tags=['FluidCMS Media'],
        summary='Delete media file',
        description='Delete a media file by ID. Removes from S3 and database.',
        responses={
            204: OpenApiResponse(description='Media deleted successfully'),
            404: OpenApiResponse(description='Media not found'),
        },
    )
    def delete(self, request, media_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        media = get_object_or_404(
            models.FluidMedia.objects.filter(tenant=tenant),
            id=media_id
        )

        # Delete file from storage
        if media.file:
            media.file.delete(save=False)

        # Delete record
        media.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Articles Repository Views
# ---------------------------------------------------------------------------


class ArticleCategoryListView(AuthenticatedAPIView):
    """List and create article categories"""

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='List article categories',
        description='Returns all categories for the tenant',
        responses={200: serializers.ArticleCategorySerializer(many=True)},
    )
    def get(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        queryset = models.ArticleCategory.objects.filter(tenant=tenant)
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        serializer = serializers.ArticleCategorySerializer(queryset, many=True)
        return Response({'categories': serializer.data})

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Create article category',
        request=serializers.ArticleCategoryWriteSerializer,
        responses={
            201: serializers.ArticleCategorySerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        serializer = serializers.ArticleCategoryWriteSerializer(
            data=request.data, context={'tenant': tenant}
        )
        serializer.is_valid(raise_exception=True)
        category = serializer.save()

        response_serializer = serializers.ArticleCategorySerializer(category)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ArticleCategoryDetailView(AuthenticatedAPIView):
    """Retrieve, update, and delete article categories"""

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Get article category',
        responses={
            200: serializers.ArticleCategorySerializer,
            404: OpenApiResponse(description='Category not found'),
        },
    )
    def get(self, request, category_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        category = get_object_or_404(
            models.ArticleCategory.objects.filter(tenant=tenant),
            id=category_id
        )
        serializer = serializers.ArticleCategorySerializer(category)
        return Response(serializer.data)

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Update article category',
        request=serializers.ArticleCategoryWriteSerializer,
        responses={
            200: serializers.ArticleCategorySerializer,
            400: OpenApiResponse(description='Validation error'),
            404: OpenApiResponse(description='Category not found'),
        },
    )
    def put(self, request, category_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        category = get_object_or_404(
            models.ArticleCategory.objects.filter(tenant=tenant),
            id=category_id
        )

        serializer = serializers.ArticleCategoryWriteSerializer(
            category, data=request.data, context={'tenant': tenant}
        )
        serializer.is_valid(raise_exception=True)
        category = serializer.save()

        response_serializer = serializers.ArticleCategorySerializer(category)
        return Response(response_serializer.data)

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Delete article category',
        responses={
            204: OpenApiResponse(description='Category deleted'),
            404: OpenApiResponse(description='Category not found'),
        },
    )
    def delete(self, request, category_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        category = get_object_or_404(
            models.ArticleCategory.objects.filter(tenant=tenant),
            id=category_id
        )
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ArticleTagListView(AuthenticatedAPIView):
    """List and create article tags"""

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='List article tags',
        description='Returns all tags for the tenant',
        responses={200: serializers.ArticleTagSerializer(many=True)},
    )
    def get(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        queryset = models.ArticleTag.objects.filter(tenant=tenant)
        serializer = serializers.ArticleTagSerializer(queryset, many=True)
        return Response({'tags': serializer.data})

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Create article tag',
        request=serializers.ArticleTagWriteSerializer,
        responses={
            201: serializers.ArticleTagSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        serializer = serializers.ArticleTagWriteSerializer(
            data=request.data, context={'tenant': tenant}
        )
        serializer.is_valid(raise_exception=True)
        tag = serializer.save()

        response_serializer = serializers.ArticleTagSerializer(tag)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ArticleTagDetailView(AuthenticatedAPIView):
    """Retrieve, update, and delete article tags"""

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Get article tag',
        responses={
            200: serializers.ArticleTagSerializer,
            404: OpenApiResponse(description='Tag not found'),
        },
    )
    def get(self, request, tag_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        tag = get_object_or_404(
            models.ArticleTag.objects.filter(tenant=tenant),
            id=tag_id
        )
        serializer = serializers.ArticleTagSerializer(tag)
        return Response(serializer.data)

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Update article tag',
        request=serializers.ArticleTagWriteSerializer,
        responses={
            200: serializers.ArticleTagSerializer,
            400: OpenApiResponse(description='Validation error'),
            404: OpenApiResponse(description='Tag not found'),
        },
    )
    def put(self, request, tag_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        tag = get_object_or_404(
            models.ArticleTag.objects.filter(tenant=tenant),
            id=tag_id
        )

        serializer = serializers.ArticleTagWriteSerializer(
            tag, data=request.data, context={'tenant': tenant}
        )
        serializer.is_valid(raise_exception=True)
        tag = serializer.save()

        response_serializer = serializers.ArticleTagSerializer(tag)
        return Response(response_serializer.data)

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Delete article tag',
        responses={
            204: OpenApiResponse(description='Tag deleted'),
            404: OpenApiResponse(description='Tag not found'),
        },
    )
    def delete(self, request, tag_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        tag = get_object_or_404(
            models.ArticleTag.objects.filter(tenant=tenant),
            id=tag_id
        )
        tag.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ArticleListView(AuthenticatedAPIView):
    """List and create articles"""

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='List articles',
        description='Returns articles for the tenant with filtering options',
        parameters=[
            OpenApiParameter('status', OpenApiTypes.STR, OpenApiParameter.QUERY,
                           description='Filter by status: draft, published, archived'),
            OpenApiParameter('category', OpenApiTypes.UUID, OpenApiParameter.QUERY,
                           description='Filter by category ID'),
            OpenApiParameter('tag', OpenApiTypes.UUID, OpenApiParameter.QUERY,
                           description='Filter by tag ID'),
        ],
        responses={200: serializers.ArticleListSerializer(many=True)},
    )
    def get(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        queryset = models.Article.objects.filter(tenant=tenant).select_related(
            'category', 'featured_image', 'author'
        ).prefetch_related('tags')

        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category_id=category)

        tag = request.query_params.get('tag')
        if tag:
            queryset = queryset.filter(tags__id=tag)

        serializer = serializers.ArticleListSerializer(queryset, many=True)
        return Response({'articles': serializer.data})

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Create article',
        request=serializers.ArticleWriteSerializer,
        responses={
            201: serializers.ArticleSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        serializer = serializers.ArticleWriteSerializer(
            data=request.data, context={'tenant': tenant, 'user': request.user}
        )
        serializer.is_valid(raise_exception=True)
        article = serializer.save()

        response_serializer = serializers.ArticleSerializer(article)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ArticleDetailView(AuthenticatedAPIView):
    """Retrieve, update, and delete articles"""

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Get article',
        responses={
            200: serializers.ArticleSerializer,
            404: OpenApiResponse(description='Article not found'),
        },
    )
    def get(self, request, article_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        article = get_object_or_404(
            models.Article.objects.filter(tenant=tenant).select_related(
                'category', 'featured_image', 'author'
            ).prefetch_related('tags'),
            id=article_id
        )
        serializer = serializers.ArticleSerializer(article)
        return Response(serializer.data)

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Update article',
        request=serializers.ArticleWriteSerializer,
        responses={
            200: serializers.ArticleSerializer,
            400: OpenApiResponse(description='Validation error'),
            404: OpenApiResponse(description='Article not found'),
        },
    )
    def put(self, request, article_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        article = get_object_or_404(
            models.Article.objects.filter(tenant=tenant),
            id=article_id
        )

        serializer = serializers.ArticleWriteSerializer(
            article, data=request.data, context={'tenant': tenant, 'user': request.user}
        )
        serializer.is_valid(raise_exception=True)
        article = serializer.save()

        response_serializer = serializers.ArticleSerializer(article)
        return Response(response_serializer.data)

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Delete article',
        responses={
            204: OpenApiResponse(description='Article deleted'),
            404: OpenApiResponse(description='Article not found'),
        },
    )
    def delete(self, request, article_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        article = get_object_or_404(
            models.Article.objects.filter(tenant=tenant),
            id=article_id
        )
        article.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ArticlePublishView(AuthenticatedAPIView):
    """Publish an article"""

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Publish article',
        responses={
            200: serializers.ArticleSerializer,
            404: OpenApiResponse(description='Article not found'),
        },
    )
    def post(self, request, article_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        article = get_object_or_404(
            models.Article.objects.filter(tenant=tenant),
            id=article_id
        )
        article.publish()

        serializer = serializers.ArticleSerializer(article)
        return Response(serializer.data)


class ArticleArchiveView(AuthenticatedAPIView):
    """Archive an article"""

    @extend_schema(
        tags=['FluidCMS Articles'],
        summary='Archive article',
        responses={
            200: serializers.ArticleSerializer,
            404: OpenApiResponse(description='Article not found'),
        },
    )
    def post(self, request, article_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        article = get_object_or_404(
            models.Article.objects.filter(tenant=tenant),
            id=article_id
        )
        article.archive()

        serializer = serializers.ArticleSerializer(article)
        return Response(serializer.data)


content_page_view = ContentPageView.as_view()
content_page_create_view = ContentPageCreateView.as_view()
content_sitemap_view = ContentSitemapView.as_view()
content_live_view = ContentLiveView.as_view()
tenant_home_view = TenantHomeView.as_view()
media_view = MediaView.as_view()
media_detail_view = MediaDetailView.as_view()

# Article views
article_category_list_view = ArticleCategoryListView.as_view()
article_category_detail_view = ArticleCategoryDetailView.as_view()
article_tag_list_view = ArticleTagListView.as_view()
article_tag_detail_view = ArticleTagDetailView.as_view()
article_list_view = ArticleListView.as_view()
article_detail_view = ArticleDetailView.as_view()
article_publish_view = ArticlePublishView.as_view()
article_archive_view = ArticleArchiveView.as_view()


# ---------------------------------------------------------------------------
# Block Catalog API
# ---------------------------------------------------------------------------


class BlockCatalogView(AuthenticatedAPIView):
    """
    Returns the block catalog for a tenant - all available block types
    from installed and active bundle versions, plus global bundles.
    """

    @extend_schema(
        tags=['FluidCMS Block Catalog'],
        summary='Get block catalog for tenant',
        description='Returns all available block types from active bundle installs and global bundles',
        parameters=[
            OpenApiParameter(
                name='category',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by category',
                required=False,
            ),
        ],
        responses={
            200: serializers.BlockCatalogEntrySerializer(many=True),
        },
    )
    def get(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        category_filter = request.query_params.get('category')

        catalog_entries = []

        active_installs = models.BundleInstall.objects.filter(
            tenant=tenant,
            status=models.BundleInstall.InstallStatus.ACTIVE
        ).select_related('bundle_version', 'bundle_version__bundle')

        for install in active_installs:
            bundle_version = install.bundle_version
            definitions = bundle_version.block_definitions.all()

            if category_filter:
                definitions = definitions.filter(category=category_filter)

            for defn in definitions:
                catalog_entries.append({
                    'block_type_id': defn.block_type_id,
                    'name': defn.name,
                    'description': defn.description,
                    'icon': defn.icon,
                    'category': defn.category,
                    'variants': defn.variants,
                    'feature_toggles': defn.feature_toggles,
                    'style_axes': defn.style_axes,
                    'content_slots': defn.content_slots,
                    'defaults': defn.defaults,
                    'bundle_name': bundle_version.bundle.name,
                    'bundle_slug': bundle_version.bundle.slug,
                    'bundle_version': bundle_version.version,
                    'bundle_version_id': bundle_version.id,
                })

        global_bundles = models.BlockBundle.objects.filter(is_global=True)
        for bundle in global_bundles:
            latest_published = bundle.versions.filter(
                status=models.BlockBundleVersion.VersionStatus.PUBLISHED
            ).order_by('-published_at').first()

            if not latest_published:
                continue

            already_installed = any(
                e['bundle_slug'] == bundle.slug for e in catalog_entries
            )
            if already_installed:
                continue

            definitions = latest_published.block_definitions.all()
            if category_filter:
                definitions = definitions.filter(category=category_filter)

            for defn in definitions:
                catalog_entries.append({
                    'block_type_id': defn.block_type_id,
                    'name': defn.name,
                    'description': defn.description,
                    'icon': defn.icon,
                    'category': defn.category,
                    'variants': defn.variants,
                    'feature_toggles': defn.feature_toggles,
                    'style_axes': defn.style_axes,
                    'content_slots': defn.content_slots,
                    'defaults': defn.defaults,
                    'bundle_name': bundle.name,
                    'bundle_slug': bundle.slug,
                    'bundle_version': latest_published.version,
                    'bundle_version_id': latest_published.id,
                })

        catalog_entries.sort(key=lambda x: (x['category'], x['name']))

        serializer = serializers.BlockCatalogEntrySerializer(catalog_entries, many=True)
        return Response(serializer.data)


block_catalog_view = BlockCatalogView.as_view()


# ---------------------------------------------------------------------------
# Bundle Management APIs
# ---------------------------------------------------------------------------


class BundleListView(AuthenticatedAPIView):
    """List and create block bundles."""

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='List bundles',
        description='List all bundles accessible to the tenant (owned + global)',
        responses={
            200: serializers.BlockBundleSerializer(many=True),
        },
    )
    def get(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        bundles = models.BlockBundle.objects.filter(
            Q(is_global=True) | Q(tenant=tenant)
        ).order_by('name')

        serializer = serializers.BlockBundleSerializer(bundles, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='Create bundle',
        description='Create a new block bundle for the tenant',
        request=serializers.BlockBundleSerializer,
        responses={
            201: serializers.BlockBundleSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        serializer = serializers.BlockBundleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bundle = models.BlockBundle(
            tenant=tenant,
            is_global=False,
            **serializer.validated_data
        )
        bundle.save()

        result_serializer = serializers.BlockBundleSerializer(bundle)
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)


class BundleDetailView(AuthenticatedAPIView):
    """Get, update, or delete a bundle."""

    def _get_bundle(self, request, bundle_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        return get_object_or_404(
            models.BlockBundle.objects.filter(
                Q(is_global=True) | Q(tenant=tenant)
            ),
            id=bundle_id
        )

    def _get_owned_bundle(self, request, bundle_id: str):
        """Get bundle that is owned by the tenant (excludes global bundles)."""
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        bundle = get_object_or_404(
            models.BlockBundle.objects.filter(
                Q(is_global=True) | Q(tenant=tenant)
            ),
            id=bundle_id
        )

        if bundle.is_global:
            raise ValidationError({
                'bundle': 'Cannot modify global bundles. Global bundles are read-only.'
            })

        return bundle

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='Get bundle details',
        responses={
            200: serializers.BlockBundleSerializer,
            404: OpenApiResponse(description='Bundle not found'),
        },
    )
    def get(self, request, bundle_id: str):
        bundle = self._get_bundle(request, bundle_id)
        serializer = serializers.BlockBundleSerializer(bundle)
        return Response(serializer.data)

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='Delete bundle',
        responses={
            204: OpenApiResponse(description='Bundle deleted'),
            404: OpenApiResponse(description='Bundle not found'),
            400: OpenApiResponse(description='Cannot delete global bundle'),
        },
    )
    def delete(self, request, bundle_id: str):
        bundle = self._get_owned_bundle(request, bundle_id)
        bundle.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BundleVersionListView(AuthenticatedAPIView):
    """List and create bundle versions."""

    def _get_bundle(self, request, bundle_id: str, require_owned: bool = False):
        """
        Get bundle accessible to the tenant.
        If require_owned=True, only returns bundles owned by the tenant (not global).
        """
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        bundle = get_object_or_404(
            models.BlockBundle.objects.filter(
                Q(is_global=True) | Q(tenant=tenant)
            ),
            id=bundle_id
        )

        if require_owned and bundle.is_global:
            raise ValidationError({
                'bundle': 'Cannot modify global bundles. Global bundles are read-only.'
            })

        return bundle

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='List bundle versions',
        responses={
            200: serializers.BlockBundleVersionSerializer(many=True),
        },
    )
    def get(self, request, bundle_id: str):
        bundle = self._get_bundle(request, bundle_id)
        versions = bundle.versions.all().order_by('-created_at')
        serializer = serializers.BlockBundleVersionSerializer(versions, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='Create bundle version',
        description='Create a new draft version of the bundle',
        request=inline_serializer(
            name='CreateBundleVersionRequest',
            fields={
                'version': drf_serializers.CharField(help_text='Semantic version (e.g., 1.0.0)'),
                'changelog': drf_serializers.CharField(required=False),
            }
        ),
        responses={
            201: serializers.BlockBundleVersionSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request, bundle_id: str):
        bundle = self._get_bundle(request, bundle_id, require_owned=True)

        version_str = request.data.get('version')
        if not version_str:
            raise ValidationError({'version': 'Version string is required'})

        existing = bundle.versions.filter(version=version_str).exists()
        if existing:
            raise ValidationError({'version': f'Version {version_str} already exists'})

        changelog = request.data.get('changelog', '')

        bundle_version = models.BlockBundleVersion.create_new_version(
            bundle=bundle,
            version=version_str,
            user=request.user,
        )
        bundle_version.changelog = changelog
        bundle_version.save()

        serializer = serializers.BlockBundleVersionSerializer(bundle_version)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BundleVersionDetailView(AuthenticatedAPIView):
    """Get or update a specific bundle version."""

    def _get_version(self, request, bundle_id: str, version_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')
        bundle = get_object_or_404(
            models.BlockBundle.objects.filter(
                Q(is_global=True) | Q(tenant=tenant)
            ),
            id=bundle_id
        )
        return get_object_or_404(bundle.versions, id=version_id)

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='Get bundle version details',
        responses={
            200: serializers.BlockBundleVersionSerializer,
            404: OpenApiResponse(description='Version not found'),
        },
    )
    def get(self, request, bundle_id: str, version_id: str):
        version = self._get_version(request, bundle_id, version_id)
        serializer = serializers.BlockBundleVersionSerializer(version)
        return Response(serializer.data)


class BundleVersionValidateView(AuthenticatedAPIView):
    """Validate a bundle version."""

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='Validate bundle version',
        description='Run validation checks on a bundle version',
        responses={
            200: inline_serializer(
                name='ValidationResponse',
                fields={
                    'is_valid': drf_serializers.BooleanField(),
                    'errors': drf_serializers.ListField(child=drf_serializers.CharField()),
                    'warnings': drf_serializers.ListField(child=drf_serializers.CharField()),
                }
            ),
        },
    )
    def post(self, request, bundle_id: str, version_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        bundle = get_object_or_404(
            models.BlockBundle.objects.filter(tenant=tenant),
            id=bundle_id
        )
        version = get_object_or_404(bundle.versions, id=version_id)

        from .services import bundle_validation_service
        result = bundle_validation_service.validate_bundle_version(version)

        return Response(result.to_dict())


class BundleVersionTransitionView(AuthenticatedAPIView):
    """Handle bundle version lifecycle transitions."""

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='Transition bundle version state',
        description='Perform a lifecycle transition (submit, reject, publish, deprecate)',
        request=inline_serializer(
            name='TransitionRequest',
            fields={
                'action': drf_serializers.ChoiceField(choices=['submit', 'reject', 'publish', 'deprecate']),
            }
        ),
        responses={
            200: serializers.BlockBundleVersionSerializer,
            400: OpenApiResponse(description='Invalid transition'),
        },
    )
    def post(self, request, bundle_id: str, version_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        bundle = get_object_or_404(
            models.BlockBundle.objects.filter(tenant=tenant),
            id=bundle_id
        )
        version = get_object_or_404(bundle.versions, id=version_id)

        action = request.data.get('action')
        if not action:
            raise ValidationError({'action': 'Action is required'})

        if action == 'submit':
            version.submit()
        elif action == 'reject':
            version.reject()
        elif action == 'publish':
            version.publish(user=request.user)
        elif action == 'deprecate':
            version.deprecate()
        else:
            raise ValidationError({'action': f"Unknown action: {action}"})

        serializer = serializers.BlockBundleVersionSerializer(version)
        return Response(serializer.data)


class BundleInstallView(AuthenticatedAPIView):
    """Manage bundle installations for a tenant."""

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='List bundle installs',
        description='List all bundle installations for the tenant',
        responses={
            200: serializers.BundleInstallSerializer(many=True),
        },
    )
    def get(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        installs = models.BundleInstall.objects.filter(
            tenant=tenant
        ).select_related('bundle_version', 'bundle_version__bundle')

        serializer = serializers.BundleInstallSerializer(installs, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='Install bundle version',
        description='Install a published bundle version for the tenant',
        request=inline_serializer(
            name='InstallBundleRequest',
            fields={
                'bundle_version_id': drf_serializers.UUIDField(),
            }
        ),
        responses={
            201: serializers.BundleInstallSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def post(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        version_id = request.data.get('bundle_version_id')
        if not version_id:
            raise ValidationError({'bundle_version_id': 'Bundle version ID is required'})

        bundle_version = get_object_or_404(
            models.BlockBundleVersion.objects.filter(
                status=models.BlockBundleVersion.VersionStatus.PUBLISHED
            ),
            id=version_id
        )

        install = models.BundleInstall(
            tenant=tenant,
            bundle_version=bundle_version,
            installed_by=request.user,
            status=models.BundleInstall.InstallStatus.ACTIVE,
        )
        install.save()

        serializer = serializers.BundleInstallSerializer(install)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BundleInstallDetailView(AuthenticatedAPIView):
    """Manage a specific bundle installation."""

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='Uninstall bundle',
        description='Remove a bundle installation from the tenant',
        responses={
            204: OpenApiResponse(description='Bundle uninstalled'),
            404: OpenApiResponse(description='Installation not found'),
        },
    )
    def delete(self, request, install_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        install = get_object_or_404(
            models.BundleInstall.objects.filter(tenant=tenant),
            id=install_id
        )
        install.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=['FluidCMS Bundles'],
        summary='Update install status',
        description='Activate or deactivate a bundle installation',
        request=inline_serializer(
            name='UpdateInstallStatusRequest',
            fields={
                'status': drf_serializers.ChoiceField(choices=['active', 'inactive']),
            }
        ),
        responses={
            200: serializers.BundleInstallSerializer,
            400: OpenApiResponse(description='Validation error'),
        },
    )
    def patch(self, request, install_id: str):
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError('Authenticated user must belong to a tenant')

        install = get_object_or_404(
            models.BundleInstall.objects.filter(tenant=tenant),
            id=install_id
        )

        new_status = request.data.get('status')
        if new_status == 'active':
            install.status = models.BundleInstall.InstallStatus.ACTIVE
        elif new_status == 'inactive':
            install.status = models.BundleInstall.InstallStatus.INACTIVE
        else:
            raise ValidationError({'status': 'Status must be "active" or "inactive"'})

        install.save()

        serializer = serializers.BundleInstallSerializer(install)
        return Response(serializer.data)


bundle_list_view = BundleListView.as_view()
bundle_detail_view = BundleDetailView.as_view()
bundle_version_list_view = BundleVersionListView.as_view()
bundle_version_detail_view = BundleVersionDetailView.as_view()
bundle_version_validate_view = BundleVersionValidateView.as_view()
bundle_version_transition_view = BundleVersionTransitionView.as_view()
bundle_install_view = BundleInstallView.as_view()
bundle_install_detail_view = BundleInstallDetailView.as_view()