from django.urls import path

from crm.api.products.views import ProductsView, ProductDetailView

urlpatterns = [
    path("", ProductsView.as_view()),
    path("<uuid:product_id>/", ProductDetailView.as_view()),
]
