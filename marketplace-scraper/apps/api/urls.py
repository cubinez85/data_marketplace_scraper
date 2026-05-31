from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'products', views.ProductViewSet, basename='product')
router.register(r'scrape-runs', views.ScrapeRunViewSet, basename='scrape-run')
router.register(r'targets', views.SearchTargetViewSet, basename='search-target')

urlpatterns = [
    path('api/v1/', include(router.urls)),
]
