"""
DRF Serializers для Marketplace Scraper API.
Оптимизированы для безопасной выгрузки данных, поддержки пагинации и фронтенд-отображения.
Все поля строго read-only (изменение целей/данных происходит только через Admin).
"""
from rest_framework import serializers
from django.utils import timezone
from apps.scrapers.models import Product, ScrapeRun, SearchTarget


class ProductSerializer(serializers.ModelSerializer):
    """Сериализатор товаров для API выгрузки и фильтрации."""
    marketplace_display = serializers.CharField(source='get_marketplace_display', read_only=True)
    in_stock_display = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'marketplace', 'marketplace_display', 'article', 'title',
            'price', 'old_price', 'currency', 'rating', 'review_count', 'url',
            'image_url', 'in_stock', 'in_stock_display', 'category', 'scraped_at', 'created_at'
        ]
        read_only_fields = fields

    def get_in_stock_display(self, obj):
        return "В наличии" if obj.in_stock else "Нет в наличии"


class ScrapeRunSerializer(serializers.ModelSerializer):
    """Сериализатор истории запусков парсеров (логи, статистика, ошибки)."""
    marketplace_display = serializers.CharField(source='get_marketplace_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    duration_seconds = serializers.SerializerMethodField()
    is_stale = serializers.SerializerMethodField()

    class Meta:
        model = ScrapeRun
        fields = [
            'id', 'marketplace', 'marketplace_display', 'status', 'status_display',
            'started_at', 'finished_at', 'duration_seconds', 'is_stale',
            'items_processed', 'error_message'
        ]
        read_only_fields = fields

    def get_duration_seconds(self, obj):
        if obj.started_at and obj.finished_at:
            return int((obj.finished_at - obj.started_at).total_seconds())
        return None

    def get_is_stale(self, obj):
        """Помечает зависшие сессии RUNNING старше 2 часов."""
        if obj.status == ScrapeRun.Status.RUNNING and obj.started_at:
            return timezone.now() - obj.started_at > timezone.timedelta(hours=2)
        return False


class SearchTargetSerializer(serializers.ModelSerializer):
    """Сериализатор целевых товаров (управление через Admin, чтение через API)."""
    marketplace_display = serializers.CharField(source='get_marketplace_display', read_only=True)
    days_since_checked = serializers.SerializerMethodField()

    class Meta:
        model = SearchTarget
        fields = [
            'id', 'marketplace', 'marketplace_display', 'article', 'search_query',
            'priority', 'is_active', 'last_checked', 'days_since_checked', 'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def get_days_since_checked(self, obj):
        if obj.last_checked:
            delta = timezone.now() - obj.last_checked
            return delta.days
        return None
