from django.db.models import Count
from rest_framework import serializers

from portal.models import Tenant
from . import models


class FluidBlockWriteSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=150)
    type = serializers.ChoiceField(choices=models.FluidBlock.BlockType.choices)
    layout = serializers.JSONField(required=False, default=dict)
    config = serializers.JSONField(required=False, default=dict)
    content = serializers.JSONField(required=False, default=dict, write_only=True)
    styling = serializers.JSONField(required=False, default=dict, write_only=True)
    locale = serializers.CharField(required=False, allow_blank=True, default='en')
    fallbackLocale = serializers.CharField(
        source='fallback_locale', required=False, allow_blank=True, default=''
    )
    order = serializers.IntegerField(required=False, default=0)
    isActive = serializers.BooleanField(source='is_active', required=False, default=True)
    metadata = serializers.JSONField(required=False, default=dict)
    status = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate_layout(self, value):
        # Accept layout as dict, ensure it's always a dict
        if value is None:
            return {}
        return value

    def validate_config(self, value):
        # Accept any valid JSON structure in config
        if value is None:
            return {}
        return value

    def validate(self, data):
        # Merge content into config if present (frontend sends 'content')
        if 'content' in data:
            content = data.pop('content')
            if content:
                config = data.get('config', {})
                # Merge content into config
                config.update(content)
                data['config'] = config
        
        # Merge styling into config if present
        if 'styling' in data:
            styling = data.pop('styling')
            if styling:
                config = data.get('config', {})
                config['styling'] = styling
                data['config'] = config
        
        # Remove status field completely (ignore it)
        data.pop('status', None)
        
        return data


class FluidBlockReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FluidBlock
        fields = [
            'id', 'key', 'type', 'layout', 'config', 'locale', 
            'fallback_locale', 'order', 'is_active', 'metadata',
            'created_at', 'updated_at'
        ]


class FluidPageUpsertSerializer(serializers.Serializer):
    slug = serializers.SlugField()
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(allow_blank=True, required=False, default='')
    layout = serializers.JSONField(required=False, default=dict)
    status = serializers.ChoiceField(choices=models.FluidPage.PageStatus.choices, required=False, default=models.FluidPage.PageStatus.DRAFT)
    isActive = serializers.BooleanField(source='is_active', required=False, default=True)
    isHome = serializers.BooleanField(source='is_home', required=False, default=False)
    defaultLocale = serializers.CharField(
        source='default_locale', required=False, allow_blank=True, default='en'
    )
    metadata = serializers.JSONField(required=False, default=dict)
    blocks = FluidBlockWriteSerializer(many=True, required=False, default=list)

    # Fields sent by frontend on POST but not used (ignored)
    id = serializers.CharField(required=False, allow_blank=True, write_only=True)
    createdAt = serializers.CharField(required=False, allow_blank=True, write_only=True)
    updatedAt = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, data):
        # Remove frontend-only fields that we don't need to process
        data.pop('id', None)
        data.pop('createdAt', None)
        data.pop('updatedAt', None)

        # Process layout object
        layout_data = data.get('layout', {})
        metadata = data.get('metadata', {})

        # Extract themeId, fontCombinationId, and siteInfo from layout
        if isinstance(layout_data, dict):
            if 'themeId' in layout_data:
                metadata['themeId'] = layout_data.pop('themeId')
            if 'fontCombinationId' in layout_data:
                metadata['fontCombinationId'] = layout_data.pop('fontCombinationId')
            if 'siteInfo' in layout_data:
                metadata['siteInfo'] = layout_data.pop('siteInfo')
            
            # Store remaining layout properties if any
            if layout_data:
                metadata['layout'] = layout_data

        # Clear the layout field as we're storing it in metadata
        data['layout'] = ''

        if metadata:
            data['metadata'] = metadata

        return data

    def create(self, validated_data):
        tenant = self.context['tenant']

        # Check if page with this slug already exists for this tenant
        if models.FluidPage.objects.filter(tenant=tenant, slug=validated_data['slug']).exists():
            raise serializers.ValidationError({'slug': 'Page with this slug already exists for this tenant.'})

        return self._apply(validated_data, tenant=tenant)

    def update(self, instance: models.FluidPage, validated_data):
        tenant = self.context['tenant']
        return self._apply(validated_data, instance=instance, tenant=tenant)

    def _apply(self, validated_data, instance: models.FluidPage = None, tenant: Tenant = None):
        import logging
        logger = logging.getLogger(__name__)

        blocks_data = validated_data.pop('blocks', [])
        logger.info(f"FluidPageUpsertSerializer._apply() - Processing {len(blocks_data)} blocks")

        is_home = validated_data.get('is_home', False)

        # Create or update page
        if instance:
            page = instance
            page.name = validated_data.get('name', page.name)
            page.description = validated_data.get('description', page.description)
            page.layout = validated_data.get('layout', '')
            page.status = validated_data.get('status', page.status)
            page.is_active = validated_data.get('is_active', page.is_active)
            page.is_home = is_home
            page.default_locale = validated_data.get('default_locale', page.default_locale)
            page.metadata = validated_data.get('metadata', page.metadata)
        else:
            page = models.FluidPage(
                tenant=tenant,
                slug=validated_data['slug'],
                name=validated_data['name'],
                description=validated_data.get('description', ''),
                layout='',
                status=validated_data.get('status', 'draft'),
                is_active=validated_data.get('is_active', True),
                is_home=is_home,
                default_locale=validated_data.get('default_locale', 'en'),
                metadata=validated_data.get('metadata', {})
            )

        # Save page first to ensure it has an ID
        page.save()

        # Ensure only one home page per tenant (after save so page has ID)
        if is_home:
            models.FluidPage.objects.filter(
                tenant=tenant or page.tenant,
                is_home=True
            ).exclude(id=page.id).update(is_home=False)
            logger.info(f"Unmarked other home pages for tenant {tenant or page.tenant}")
        logger.info(f"Page saved: {page.slug}, layout={page.layout}, metadata={page.metadata}")

        # Keep track of existing blocks by (key, locale) for updates
        existing_blocks = {
            (block.key, block.locale): block 
            for block in page.blocks.all()
        }
        logger.info(f"Found {len(existing_blocks)} existing blocks")
        retained_keys = set()

        for idx, block_data in enumerate(blocks_data):
            logger.info(f"Processing block {idx}: {block_data}")

            key = block_data['key']
            locale = block_data.get('locale', 'en')
            block_key = (key, locale)

            # Update existing or create new
            is_new = block_key not in existing_blocks
            block = existing_blocks.get(block_key) or models.FluidBlock(
                tenant=tenant,
                page=page,
                key=key,
                locale=locale
            )
            logger.info(f"  Block ({key}, {locale}) - {'NEW' if is_new else 'UPDATE'}")

            block.type = block_data['type']
            block.layout = block_data.get('layout', '')
            block.config = block_data.get('config', {})
            block.fallback_locale = block_data.get('fallback_locale', '')
            block.order = block_data.get('order', 0)
            block.is_active = block_data.get('is_active', True)
            block.metadata = block_data.get('metadata', {})

            block.save()
            logger.info(f"  Block saved: id={block.id}, type={block.type}")

            retained_keys.add(block_key)

        # Delete blocks not in the payload
        deleted_count = 0
        for block_key, block in existing_blocks.items():
            if block_key not in retained_keys:
                logger.info(f"Deleting block {block_key}")
                block.delete()
                deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} blocks not in payload")

        final_count = page.blocks.count()
        logger.info(f"Final state - Page: {page.slug}, Total blocks: {final_count}")
        return page


class FluidPageReadSerializer(serializers.ModelSerializer):
    blocks = FluidBlockReadSerializer(many=True, read_only=True)

    class Meta:
        model = models.FluidPage
        fields = [
            'id', 'slug', 'name', 'description', 'layout', 'status',
            'is_active', 'is_home', 'default_locale', 'metadata',
            'blocks', 'created_at', 'updated_at'
        ]


class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Topic
        fields = (
            "slug",
            "title",
            "short_description",
            "icon",
            "color",
            "image",
            "marketing_copy",
            "benefits",
            "use_cases",
            "pricing_tiers",
            "features",
            "cta",
            "markdown",
            "metadata",
        )


class SessionUpsertSerializer(serializers.Serializer):
    sessionId = serializers.UUIDField(required=False)
    referral = serializers.CharField(required=False, allow_blank=True)
    utm = serializers.JSONField(required=False, default=dict)
    metadata = serializers.JSONField(required=False, default=dict)


class AgentChatRequestSerializer(serializers.Serializer):
    sessionId = serializers.UUIDField()
    message = serializers.CharField()
    topic = serializers.SlugField(required=False, allow_blank=True)


class LikeRequestSerializer(serializers.Serializer):
    sessionId = serializers.UUIDField()
    messageIndex = serializers.IntegerField(min_value=0)
    topic = serializers.SlugField(required=False, allow_blank=True)


class EmailSendRequestSerializer(serializers.Serializer):
    sessionId = serializers.UUIDField(required=False)
    email = serializers.EmailField()
    includeSummary = serializers.BooleanField(required=False, default=True)
    subject = serializers.CharField(required=False, allow_blank=True)
    body = serializers.CharField(required=False, allow_blank=True)


class WhatsAppSendRequestSerializer(serializers.Serializer):
    sessionId = serializers.UUIDField(required=False)
    phone = serializers.CharField()
    template = serializers.CharField(required=False, allow_blank=True)
    payload = serializers.JSONField(required=False, default=dict)
    deepLink = serializers.CharField(required=False, allow_blank=True)
    prepareOnly = serializers.BooleanField(required=False, default=True)


class MeetingScheduleRequestSerializer(serializers.Serializer):
    sessionId = serializers.UUIDField(required=False)
    attendee = serializers.DictField(child=serializers.CharField(), default=dict)
    provider = serializers.CharField(required=False, allow_blank=True)
    scheduledFor = serializers.CharField()
    calendarUrl = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)


class TrackTopicVisitRequestSerializer(serializers.Serializer):
    sessionId = serializers.UUIDField()
    topic = serializers.SlugField()


class VisitorSessionSerializer(serializers.ModelSerializer):
    topic_visits_count = serializers.SerializerMethodField()
    likes_count = serializers.SerializerMethodField()
    engagement_score = serializers.SerializerMethodField()
    contact_id = serializers.SerializerMethodField()

    class Meta:
        model = models.VisitorSession
        fields = (
            "id",
            "contact_id",
            "referral_source",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "metadata",
            "total_messages",
            "created_at",
            "updated_at",
            "last_engaged_at",
            "topic_visits_count",
            "likes_count",
            "engagement_score",
            "contact_id",
        )
        read_only_fields = (
            "total_messages",
            "created_at",
            "updated_at",
            "last_engaged_at",
            "topic_visits_count",
            "likes_count",
            "engagement_score",
        )

    def get_topic_visits_count(self, obj):
        return obj.topic_visits.count()

    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_engagement_score(self, obj):
        visits = self.get_topic_visits_count(obj)
        likes = self.get_likes_count(obj)
        return visits * 2 + likes * 3 + obj.total_messages

    def get_contact_id(self, obj):
        return str(obj.contact_id) if obj.contact_id else None


class TopicAnalyticsSerializer(serializers.Serializer):
    slug = serializers.CharField()
    title = serializers.CharField()
    visits = serializers.IntegerField()


class SessionAnalyticsSerializer(serializers.Serializer):
    session = VisitorSessionSerializer()
    topics = TopicAnalyticsSerializer(many=True)
    likes = serializers.IntegerField()
    engagement_score = serializers.IntegerField()


class ConversationTurnSerializer(serializers.ModelSerializer):
    topic = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = models.ConversationTurn
        fields = ("id", "session", "topic", "user_message", "assistant_message", "suggestions", "created_at")
        read_only_fields = fields


class LikeSerializer(serializers.ModelSerializer):
    topic = serializers.SlugRelatedField(
        slug_field="slug", queryset=models.Topic.objects.all(), allow_null=True, required=False
    )
    message = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = models.Like
        fields = ("id", "session", "topic", "message_index", "message", "created_at")
        read_only_fields = ("id", "created_at", "message")


class EmailLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.EmailLog
        fields = ("id", "session", "recipient", "subject", "body", "summary_included", "sent_at")
        read_only_fields = ("id", "sent_at")


class WhatsAppLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.WhatsAppLog
        fields = (
            "id",
            "session",
            "recipient",
            "status",
            "template_name",
            "deep_link",
            "payload",
            "sent_at",
        )
        read_only_fields = ("id", "sent_at")


class MeetingBookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MeetingBooking
        fields = (
            "id",
            "session",
            "attendee_name",
            "attendee_email",
            "provider",
            "scheduled_for",
            "confirmation_message",
            "calendar_url",
            "metadata",
            "created_at",
        )
        read_only_fields = ("id", "confirmation_message", "calendar_url", "created_at")


class ConversationSerializer(serializers.ModelSerializer):
    topic = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = models.Conversation
        fields = (
            "id",
            "session",
            "topic",
            "conversation_date",
            "started_at",
            "last_message_at",
            "metadata",
        )
        read_only_fields = fields


class ConversationMessageSerializer(serializers.ModelSerializer):
    topic = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = models.ConversationMessage
        fields = (
            "id",
            "conversation",
            "session",
            "topic",
            "role",
            "content",
            "suggestions",
            "metadata",
            "conversation_sequence",
            "session_sequence",
            "created_at",
        )
        read_only_fields = fields


class FluidMediaSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = models.FluidMedia
        fields = (
            'id',
            'filename',
            'type',
            'mime_type',
            'size',
            'url',
            'metadata',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'url', 'created_at', 'updated_at')

    def get_url(self, obj):
        return obj.url


class FluidMediaUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    metadata = serializers.JSONField(required=False, default=dict)

    def validate_file(self, value):
        max_size = 50 * 1024 * 1024  # 50MB
        if value.size > max_size:
            raise serializers.ValidationError(f'File size exceeds maximum of 50MB')
        return value


# ---------------------------------------------------------------------------
# Articles Repository Serializers
# ---------------------------------------------------------------------------


class ArticleCategorySerializer(serializers.ModelSerializer):
    children_count = serializers.SerializerMethodField()
    articles_count = serializers.SerializerMethodField()

    class Meta:
        model = models.ArticleCategory
        fields = (
            'id',
            'name',
            'slug',
            'description',
            'parent',
            'order',
            'is_active',
            'children_count',
            'articles_count',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_children_count(self, obj):
        return obj.children.count()

    def get_articles_count(self, obj):
        return obj.articles.count()


class ArticleCategoryWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    slug = serializers.SlugField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    parent = serializers.UUIDField(required=False, allow_null=True)
    order = serializers.IntegerField(required=False, default=0)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_parent(self, value):
        if value is None:
            return None
        tenant = self.context.get('tenant')
        try:
            return models.ArticleCategory.objects.get(id=value, tenant=tenant)
        except models.ArticleCategory.DoesNotExist:
            raise serializers.ValidationError('Parent category not found')

    def validate(self, data):
        tenant = self.context.get('tenant')
        slug = data.get('slug')
        instance = self.instance

        qs = models.ArticleCategory.objects.filter(tenant=tenant, slug=slug)
        if instance:
            qs = qs.exclude(id=instance.id)
        if qs.exists():
            raise serializers.ValidationError({'slug': 'Category with this slug already exists'})
        return data

    def create(self, validated_data):
        tenant = self.context['tenant']
        return models.ArticleCategory.objects.create(tenant=tenant, **validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ArticleTagSerializer(serializers.ModelSerializer):
    articles_count = serializers.SerializerMethodField()

    class Meta:
        model = models.ArticleTag
        fields = (
            'id',
            'name',
            'slug',
            'color',
            'articles_count',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_articles_count(self, obj):
        return obj.articles.count()


class ArticleTagWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    slug = serializers.SlugField(max_length=100)
    color = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, data):
        tenant = self.context.get('tenant')
        slug = data.get('slug')
        instance = self.instance

        qs = models.ArticleTag.objects.filter(tenant=tenant, slug=slug)
        if instance:
            qs = qs.exclude(id=instance.id)
        if qs.exists():
            raise serializers.ValidationError({'slug': 'Tag with this slug already exists'})
        return data

    def create(self, validated_data):
        tenant = self.context['tenant']
        return models.ArticleTag.objects.create(tenant=tenant, **validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ArticleSerializer(serializers.ModelSerializer):
    category = ArticleCategorySerializer(read_only=True)
    tags = ArticleTagSerializer(many=True, read_only=True)
    featured_image = FluidMediaSerializer(read_only=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = models.Article
        fields = (
            'id',
            'title',
            'slug',
            'excerpt',
            'content',
            'category',
            'tags',
            'featured_image',
            'author',
            'author_name',
            'status',
            'published_at',
            'metadata',
            'view_count',
            'reading_time_minutes',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'view_count', 'reading_time_minutes', 'created_at', 'updated_at')

    def get_author_name(self, obj):
        if obj.author:
            return obj.author.get_full_name() or obj.author.email
        return None


class ArticleListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for article lists"""
    category_name = serializers.SerializerMethodField()
    tags_list = serializers.SerializerMethodField()
    featured_image_url = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = models.Article
        fields = (
            'id',
            'title',
            'slug',
            'excerpt',
            'category_name',
            'tags_list',
            'featured_image_url',
            'author_name',
            'status',
            'published_at',
            'view_count',
            'reading_time_minutes',
            'created_at',
        )

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_tags_list(self, obj):
        return [{'id': str(t.id), 'name': t.name, 'slug': t.slug, 'color': t.color} for t in obj.tags.all()]

    def get_featured_image_url(self, obj):
        return obj.featured_image.url if obj.featured_image else None

    def get_author_name(self, obj):
        if obj.author:
            return obj.author.get_full_name() or obj.author.email
        return None


class ArticleWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300)
    slug = serializers.SlugField(max_length=300)
    excerpt = serializers.CharField(required=False, allow_blank=True, default='')
    content = serializers.CharField(required=False, allow_blank=True, default='')
    category = serializers.UUIDField(required=False, allow_null=True)
    tags = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    featured_image = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=models.Article.ArticleStatus.choices,
        required=False,
        default=models.Article.ArticleStatus.DRAFT
    )
    metadata = serializers.JSONField(required=False, default=dict)

    def validate_category(self, value):
        if value is None:
            return None
        tenant = self.context.get('tenant')
        try:
            return models.ArticleCategory.objects.get(id=value, tenant=tenant)
        except models.ArticleCategory.DoesNotExist:
            raise serializers.ValidationError('Category not found')

    def validate_tags(self, value):
        if not value:
            return []
        tenant = self.context.get('tenant')
        tags = models.ArticleTag.objects.filter(id__in=value, tenant=tenant)
        if tags.count() != len(value):
            raise serializers.ValidationError('One or more tags not found')
        return list(tags)

    def validate_featured_image(self, value):
        if value is None:
            return None
        tenant = self.context.get('tenant')
        try:
            return models.FluidMedia.objects.get(id=value, tenant=tenant)
        except models.FluidMedia.DoesNotExist:
            raise serializers.ValidationError('Featured image not found')

    def validate(self, data):
        tenant = self.context.get('tenant')
        slug = data.get('slug')
        instance = self.instance

        qs = models.Article.objects.filter(tenant=tenant, slug=slug)
        if instance:
            qs = qs.exclude(id=instance.id)
        if qs.exists():
            raise serializers.ValidationError({'slug': 'Article with this slug already exists'})
        return data

    def create(self, validated_data):
        from django.utils import timezone

        tenant = self.context['tenant']
        user = self.context.get('user')
        tags = validated_data.pop('tags', [])

        article = models.Article(
            tenant=tenant,
            author=user,
            **validated_data
        )
        article.reading_time_minutes = article.calculate_reading_time()

        if article.status == models.Article.ArticleStatus.PUBLISHED and not article.published_at:
            article.published_at = timezone.now()

        article.save()
        if tags:
            article.tags.set(tags)
        return article

    def update(self, instance, validated_data):
        from django.utils import timezone

        tags = validated_data.pop('tags', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.reading_time_minutes = instance.calculate_reading_time()

        if instance.status == models.Article.ArticleStatus.PUBLISHED and not instance.published_at:
            instance.published_at = timezone.now()

        instance.save()

        if tags is not None:
            instance.tags.set(tags)

        return instance


# ---------------------------------------------------------------------------
# Block Bundle System Serializers
# ---------------------------------------------------------------------------


class BlockDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.BlockDefinition
        fields = (
            'id',
            'block_type_id',
            'name',
            'description',
            'icon',
            'category',
            'variants',
            'feature_toggles',
            'style_axes',
            'content_slots',
            'defaults',
            'preview_template',
            'metadata',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class BlockBundleVersionSerializer(serializers.ModelSerializer):
    block_definitions = BlockDefinitionSerializer(many=True, read_only=True)
    bundle_name = serializers.CharField(source='bundle.name', read_only=True)
    bundle_slug = serializers.CharField(source='bundle.slug', read_only=True)

    class Meta:
        model = models.BlockBundleVersion
        fields = (
            'id',
            'bundle',
            'bundle_name',
            'bundle_slug',
            'version',
            'changelog',
            'status',
            'manifest',
            'compatibility_range',
            'published_at',
            'block_definitions',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'published_at', 'created_at', 'updated_at')


class BlockBundleSerializer(serializers.ModelSerializer):
    latest_version = serializers.SerializerMethodField()
    versions_count = serializers.SerializerMethodField()

    class Meta:
        model = models.BlockBundle
        fields = (
            'id',
            'name',
            'slug',
            'description',
            'author',
            'is_global',
            'tenant',
            'latest_version',
            'versions_count',
            'metadata',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_latest_version(self, obj):
        latest = obj.versions.filter(
            status=models.BlockBundleVersion.VersionStatus.PUBLISHED
        ).order_by('-published_at').first()
        if latest:
            return {
                'id': str(latest.id),
                'version': latest.version,
                'published_at': latest.published_at,
            }
        return None

    def get_versions_count(self, obj):
        return obj.versions.count()


class BundleInstallSerializer(serializers.ModelSerializer):
    bundle_name = serializers.CharField(source='bundle_version.bundle.name', read_only=True)
    bundle_slug = serializers.CharField(source='bundle_version.bundle.slug', read_only=True)
    version = serializers.CharField(source='bundle_version.version', read_only=True)

    class Meta:
        model = models.BundleInstall
        fields = (
            'id',
            'tenant',
            'bundle_version',
            'bundle_name',
            'bundle_slug',
            'version',
            'status',
            'installed_at',
            'activated_at',
            'metadata',
        )
        read_only_fields = ('id', 'tenant', 'installed_at', 'activated_at')


class BlockCatalogEntrySerializer(serializers.Serializer):
    block_type_id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    icon = serializers.CharField()
    category = serializers.CharField()
    variants = serializers.ListField()
    feature_toggles = serializers.ListField()
    style_axes = serializers.DictField()
    content_slots = serializers.ListField()
    defaults = serializers.DictField()
    bundle_name = serializers.CharField()
    bundle_slug = serializers.CharField()
    bundle_version = serializers.CharField()
    bundle_version_id = serializers.UUIDField()


class PageVersionSerializer(serializers.ModelSerializer):
    page_slug = serializers.CharField(source='page.slug', read_only=True)
    page_name = serializers.CharField(source='page.name', read_only=True)
    published_by_name = serializers.SerializerMethodField()

    class Meta:
        model = models.PageVersion
        fields = (
            'id',
            'page',
            'page_slug',
            'page_name',
            'version_number',
            'composition',
            'content_pins',
            'published_by',
            'published_by_name',
            'published_at',
            'metadata',
        )
        read_only_fields = ('id', 'version_number', 'published_at')

    def get_published_by_name(self, obj):
        if obj.published_by:
            return obj.published_by.get_full_name() or obj.published_by.email
        return None