from django.urls import path

from . import views

app_name = "fluidcommerce"

urlpatterns = [
    path("brands/", views.BrandListView.as_view(), name="brand-list"),
    path("brands/<str:brand_id>/", views.BrandDetailView.as_view(), name="brand-detail"),
    
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path("categories/<str:category_id>/", views.CategoryDetailView.as_view(), name="category-detail"),
    
    path("attributes/", views.AttributeDefinitionListView.as_view(), name="attribute-list"),
    path("attributes/<str:attribute_id>/", views.AttributeDefinitionDetailView.as_view(), name="attribute-detail"),
    path("attributes/<str:attribute_id>/options/", views.AttributeOptionListView.as_view(), name="attribute-option-list"),
    path("attributes/<str:attribute_id>/options/<str:option_id>/", views.AttributeOptionDetailView.as_view(), name="attribute-option-detail"),
    
    path("products/", views.ProductListView.as_view(), name="product-list"),
    path("products/<str:product_id>/", views.ProductDetailView.as_view(), name="product-detail"),
    path("products/<str:product_id>/variants/", views.ProductVariantListView.as_view(), name="product-variant-list"),
    path("products/<str:product_id>/variants/<str:variant_id>/", views.ProductVariantDetailView.as_view(), name="product-variant-detail"),
    path("products/<str:product_id>/media/", views.ProductMediaListView.as_view(), name="product-media-list"),
    path("products/<str:product_id>/media/<str:media_id>/", views.ProductMediaDetailView.as_view(), name="product-media-detail"),
    
    path("orders/", views.OrderListView.as_view(), name="order-list"),
    path("orders/<str:order_id>/", views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:order_id>/<str:action>/", views.OrderActionView.as_view(), name="order-action"),
]
