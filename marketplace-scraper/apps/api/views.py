"""
DRF ViewSets для Marketplace Scraper API.
Все эндпоинты read-only. Изменение данных происходит только через Django Admin.
Поддерживает фильтрацию, полнотекстовый поиск и кастомные сводки.
"""
from rest_framework import viewsets, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Avg
from django.utils import timezone
from datetime import timedelta

from apps.scrapers.models import Product, ScrapeRun, SearchTarget
from .serializers import ProductSerializer, ScrapeRunSerializer, SearchTargetSerializer


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API товаров с фильтрацией, поиском и сортировкой.
    
    Query-параметры:
      - marketplace: wb | ozon
      - price_min, price_max: диапазон цен (float)
      - in_stock: true | false
      - search: поиск по title, article, category, marketplace
      - ordering: price, -price, scraped_at, -scraped_at, rating, -rating
    """
    queryset = Product.objects.all().order_by('-scraped_at')
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'article', 'category', 'marketplace']
    ordering_fields = ['price', 'scraped_at', 'rating', 'review_count']
    ordering = ['-scraped_at']

    def get_queryset(self):
        qs = super().get_queryset()
        request = self.request

        # Фильтр по маркетплейсу
        marketplace = request.query_params.get('marketplace')
        if marketplace:
            qs = qs.filter(marketplace=marketplace)

        # Диапазон цен
        for param, lookup in [('price_min', 'price__gte'), ('price_max', 'price__lte')]:
            val = request.query_params.get(param)
            if val is not None:
                try:
                    qs = qs.filter(**{lookup: float(val)})
                except (ValueError, TypeError):
                    pass

        # Наличие
        in_stock = request.query_params.get('in_stock')
        if in_stock is not None:
            qs = qs.filter(in_stock=in_stock.lower() == 'true')

        return qs

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Быстрая статистика по товарам"""
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        qs = self.get_queryset()

        return Response({
            'total_products': qs.count(),
            'wb_count': qs.filter(marketplace='wb').count(),
            'ozon_count': qs.filter(marketplace='ozon').count(),
            'updated_last_24h': qs.filter(scraped_at__gte=last_24h).count(),
            'avg_rating': round(qs.aggregate(Avg('rating'))['rating__avg'] or 0.0, 2),
            'in_stock_count': qs.filter(in_stock=True).count(),
        })


class ScrapeRunViewSet(viewsets.ReadOnlyModelViewSet):
    """
    История запусков парсеров (логи, статус, метрики).
    
    Query-параметры:
      - marketplace: wb | ozon
      - status: running | success | failed
      - ordering: -started_at, items_processed, -duration_seconds
    """
    queryset = ScrapeRun.objects.all().order_by('-started_at')
    serializer_class = ScrapeRunSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['marketplace', 'status']
    ordering_fields = ['started_at', 'finished_at', 'items_processed']
    ordering = ['-started_at']

    def get_queryset(self):
        qs = super().get_queryset()
        marketplace = self.request.query_params.get('marketplace')
        if marketplace:
            qs = qs.filter(marketplace=marketplace)
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


class SearchTargetViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Целевые товары для парсинга (только активные).
    
    Query-параметры:
      - search: поиск по article или search_query
      - marketplace: wb | ozon
    """
    queryset = SearchTarget.objects.filter(is_active=True).order_by('priority', 'created_at')
    serializer_class = SearchTargetSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter]
    search_fields = ['article', 'search_query', 'marketplace']

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Сводка по активным целям и последней проверке"""
        qs = self.get_queryset()
        latest_checked = qs.order_by('-last_checked').first()
        
        return Response({
            'active_targets': qs.count(),
            'wb_targets': qs.filter(marketplace='wb').count(),
            'ozon_targets': qs.filter(marketplace='ozon').count(),
            'last_checked': latest_checked.last_checked if latest_checked else None,
            'oldest_unchecked': qs.filter(last_checked__isnull=True).count(),
        })
