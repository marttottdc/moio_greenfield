
from django.urls import path

from . import views

urlpatterns = [
    path("content/pages", views.content_page_create_view, name="api-content-page-create"),
    path("content/pages/<uuid:page_id>", views.content_page_view, name="api-content-page"),
    path("content/pages/<uuid:page_id>/", views.content_page_view, name="api-content-page-trailing"),
    path("content/live/<uuid:page_id>", views.content_live_view, name="api-content-live"),
    path("content/live/<uuid:page_id>/", views.content_live_view, name="api-content-live-trailing"),
    path("content/sitemap", views.content_sitemap_view, name="api-content-sitemap"),
    path("tenants/<str:subdomain>", views.tenant_home_view, name="api-tenant-home"),
    path("tenants/<str:subdomain>/", views.tenant_home_view, name="api-tenant-home-trailing"),
    path("media/", views.media_view, name="api-media"),
    path("media/<uuid:media_id>", views.media_detail_view, name="api-media-detail"),
    path("media/<uuid:media_id>/", views.media_detail_view, name="api-media-detail-trailing"),

    # Article Categories
    path("articles/categories", views.article_category_list_view, name="api-article-categories"),
    path("articles/categories/", views.article_category_list_view, name="api-article-categories-trailing"),
    path("articles/categories/<uuid:category_id>", views.article_category_detail_view, name="api-article-category-detail"),
    path("articles/categories/<uuid:category_id>/", views.article_category_detail_view, name="api-article-category-detail-trailing"),

    # Article Tags
    path("articles/tags", views.article_tag_list_view, name="api-article-tags"),
    path("articles/tags/", views.article_tag_list_view, name="api-article-tags-trailing"),
    path("articles/tags/<uuid:tag_id>", views.article_tag_detail_view, name="api-article-tag-detail"),
    path("articles/tags/<uuid:tag_id>/", views.article_tag_detail_view, name="api-article-tag-detail-trailing"),

    # Articles
    path("articles", views.article_list_view, name="api-articles"),
    path("articles/", views.article_list_view, name="api-articles-trailing"),
    path("articles/<uuid:article_id>", views.article_detail_view, name="api-article-detail"),
    path("articles/<uuid:article_id>/", views.article_detail_view, name="api-article-detail-trailing"),
    path("articles/<uuid:article_id>/publish", views.article_publish_view, name="api-article-publish"),
    path("articles/<uuid:article_id>/publish/", views.article_publish_view, name="api-article-publish-trailing"),
    path("articles/<uuid:article_id>/archive", views.article_archive_view, name="api-article-archive"),
    path("articles/<uuid:article_id>/archive/", views.article_archive_view, name="api-article-archive-trailing"),

    # Block Catalog
    path("blocks/catalog", views.block_catalog_view, name="api-block-catalog"),
    path("blocks/catalog/", views.block_catalog_view, name="api-block-catalog-trailing"),

    # Bundle Management
    path("bundles", views.bundle_list_view, name="api-bundles"),
    path("bundles/", views.bundle_list_view, name="api-bundles-trailing"),
    path("bundles/<uuid:bundle_id>", views.bundle_detail_view, name="api-bundle-detail"),
    path("bundles/<uuid:bundle_id>/", views.bundle_detail_view, name="api-bundle-detail-trailing"),
    path("bundles/<uuid:bundle_id>/versions", views.bundle_version_list_view, name="api-bundle-versions"),
    path("bundles/<uuid:bundle_id>/versions/", views.bundle_version_list_view, name="api-bundle-versions-trailing"),
    path("bundles/<uuid:bundle_id>/versions/<uuid:version_id>", views.bundle_version_detail_view, name="api-bundle-version-detail"),
    path("bundles/<uuid:bundle_id>/versions/<uuid:version_id>/", views.bundle_version_detail_view, name="api-bundle-version-detail-trailing"),
    path("bundles/<uuid:bundle_id>/versions/<uuid:version_id>/validate", views.bundle_version_validate_view, name="api-bundle-version-validate"),
    path("bundles/<uuid:bundle_id>/versions/<uuid:version_id>/validate/", views.bundle_version_validate_view, name="api-bundle-version-validate-trailing"),
    path("bundles/<uuid:bundle_id>/versions/<uuid:version_id>/transition", views.bundle_version_transition_view, name="api-bundle-version-transition"),
    path("bundles/<uuid:bundle_id>/versions/<uuid:version_id>/transition/", views.bundle_version_transition_view, name="api-bundle-version-transition-trailing"),

    # Bundle Installations
    path("bundle-installs", views.bundle_install_view, name="api-bundle-installs"),
    path("bundle-installs/", views.bundle_install_view, name="api-bundle-installs-trailing"),
    path("bundle-installs/<uuid:install_id>", views.bundle_install_detail_view, name="api-bundle-install-detail"),
    path("bundle-installs/<uuid:install_id>/", views.bundle_install_detail_view, name="api-bundle-install-detail-trailing"),
]
