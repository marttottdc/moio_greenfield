from django.urls import path, include
from rest_framework.routers import SimpleRouter
from crm.api.auth.views import AuthViewSet


router = SimpleRouter()
router.register(r'', AuthViewSet, basename='auth')


urlpatterns = [
    path('', include(router.urls)),
]