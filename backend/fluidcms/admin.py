from django.contrib import admin

from . import models


@admin.register(models.FluidPage)
class FluidPageAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'tenant', 'status', 'is_home', 'is_active', 'created_at')
    list_filter = ('tenant', 'status', 'is_home', 'is_active')
    search_fields = ('slug', 'name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('id', 'tenant', 'slug', 'name', 'description')
        }),
        ('Settings', {
            'fields': ('layout', 'status', 'is_active', 'is_home', 'default_locale')
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(models.FluidBlock)
class FluidBlockAdmin(admin.ModelAdmin):
    list_display = ('key', 'type', 'page', 'tenant', 'locale', 'order', 'is_active')
    list_filter = ('tenant', 'type', 'is_active', 'locale')
    search_fields = ('key', 'page__slug', 'page__name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('id', 'tenant', 'page', 'key', 'type')
        }),
        ('Content', {
            'fields': ('layout', 'config', 'locale', 'fallback_locale')
        }),
        ('Display', {
            'fields': ('order', 'is_active')
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(models.VisitorSession)
class VisitorSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "referral_source", "utm_source", "total_messages", "updated_at")
    search_fields = ("id", "referral_source", "utm_source", "utm_medium", "utm_campaign")
    readonly_fields = ("created_at", "updated_at", "last_engaged_at")


@admin.register(models.Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "color")
    search_fields = ("slug", "title")
    readonly_fields = ("created_at", "updated_at")


@admin.register(models.TopicVisit)
class TopicVisitAdmin(admin.ModelAdmin):
    list_display = ("session", "topic", "visited_at")
    search_fields = ("session__id", "topic__slug")
    readonly_fields = ("visited_at",)


@admin.register(models.ConversationTurn)
class ConversationTurnAdmin(admin.ModelAdmin):
    list_display = ("session", "topic", "created_at")
    search_fields = ("session__id", "topic__slug", "user_message")
    readonly_fields = ("created_at",)


@admin.register(models.Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ("session", "topic", "message_index", "created_at")
    search_fields = ("session__id", "topic__slug")
    readonly_fields = ("created_at",)


@admin.register(models.EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ("recipient", "session", "summary_included", "sent_at")
    search_fields = ("recipient", "session__id")
    readonly_fields = ("sent_at",)


@admin.register(models.WhatsAppLog)
class WhatsAppLogAdmin(admin.ModelAdmin):
    list_display = ("recipient", "status", "sent_at")
    search_fields = ("recipient", "status")
    readonly_fields = ("sent_at",)


@admin.register(models.MeetingBooking)
class MeetingBookingAdmin(admin.ModelAdmin):
    list_display = ("attendee_name", "provider", "scheduled_for", "created_at")
    search_fields = ("attendee_name", "attendee_email")
    readonly_fields = ("created_at",)


@admin.register(models.Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = (
        "session",
        "topic",
        "conversation_date",
        "started_at",
        "last_message_at",
    )
    search_fields = ("session__id", "topic__slug")
    list_filter = ("conversation_date",)
    raw_id_fields = ("session", "topic")
    readonly_fields = ("started_at", "last_message_at")


@admin.register(models.ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = (
        "conversation",
        "session",
        "topic",
        "role",
        "conversation_sequence",
        "created_at",
    )
    search_fields = (
        "conversation__id",
        "session__id",
        "topic__slug",
        "content",
    )
    list_filter = ("role",)
    raw_id_fields = ("conversation", "session", "topic")
    readonly_fields = ("created_at",)


@admin.register(models.FluidMedia)
class FluidMediaAdmin(admin.ModelAdmin):
    list_display = ('filename', 'tenant', 'type', 'mime_type', 'size', 'created_at')
    list_filter = ('tenant', 'type')
    search_fields = ('filename',)
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(models.ArticleCategory)
class ArticleCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'tenant', 'parent', 'order', 'is_active', 'created_at')
    list_filter = ('tenant', 'is_active')
    search_fields = ('name', 'slug')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('id', 'tenant', 'name', 'slug', 'description')
        }),
        ('Hierarchy', {
            'fields': ('parent', 'order')
        }),
        ('Settings', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(models.ArticleTag)
class ArticleTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'tenant', 'color', 'created_at')
    list_filter = ('tenant',)
    search_fields = ('name', 'slug')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(models.Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'tenant', 'author', 'category', 'status', 'published_at', 'view_count')
    list_filter = ('tenant', 'status', 'category')
    search_fields = ('title', 'slug', 'excerpt', 'content')
    readonly_fields = ('id', 'view_count', 'reading_time_minutes', 'created_at', 'updated_at')
    raw_id_fields = ('author', 'category', 'featured_image')
    filter_horizontal = ('tags',)
    fieldsets = (
        (None, {
            'fields': ('id', 'tenant', 'author', 'title', 'slug')
        }),
        ('Content', {
            'fields': ('excerpt', 'content', 'featured_image')
        }),
        ('Classification', {
            'fields': ('category', 'tags')
        }),
        ('Publishing', {
            'fields': ('status', 'published_at')
        }),
        ('Metadata', {
            'fields': ('metadata', 'view_count', 'reading_time_minutes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )