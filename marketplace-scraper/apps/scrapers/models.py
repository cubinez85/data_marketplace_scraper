"""
Модели для хранения результатов скрапинга и логирования запусков.
Адаптировано под PostgreSQL (JSONField, Decimal, индексы).
"""
from django.db import models
from django.utils import timezone


class Marketplace(models.TextChoices):
    WILDBERRIES = "wb", "Wildberries"
    OZON = "ozon", "Ozon"


class ScrapeRun(models.Model):
    """Журнал запусков парсеров. Полезно для мониторинга и отладки."""
    class Status(models.TextChoices):
        RUNNING = "running", "Выполняется"
        SUCCESS = "success", "Успешно"
        FAILED = "failed", "Ошибка"

    marketplace = models.CharField(
        max_length=10, choices=Marketplace.choices, db_index=True
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.RUNNING
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    items_processed = models.PositiveIntegerField(default=0, verbose_name="Обработано товаров")
    error_message = models.TextField(blank=True, null=True, verbose_name="Текст ошибки")

    class Meta:
        verbose_name = "Сессия скрапинга"
        verbose_name_plural = "Сессии скрапинга"
        ordering = ["-started_at"]

    def __str__(self):
        status_label = self.get_status_display()
        return f"{self.get_marketplace_display()} | {status_label} | {self.started_at:%d.%m.%Y %H:%M}"


class Product(models.Model):
    """Основная модель товара с маркетплейсов."""
    marketplace = models.CharField(
        max_length=10, choices=Marketplace.choices, db_index=True
    )
    vendor_sku = models.CharField(
        max_length=100, db_index=True, verbose_name="Артикул / ID товара",
        help_text="WB: nm_id, Ozon: sku или product_id"
    )
    title = models.CharField(max_length=500, verbose_name="Название товара")
    price = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Текущая цена"
    )
    old_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name="Старая цена (до скидки)"
    )
    currency = models.CharField(max_length=3, default="RUB", verbose_name="Валюта")
    rating = models.FloatField(null=True, blank=True, verbose_name="Рейтинг")
    review_count = models.PositiveIntegerField(default=0, verbose_name="Количество отзывов")
    url = models.URLField(max_length=500, verbose_name="Ссылка на товар")
    image_url = models.URLField(max_length=500, null=True, blank=True, verbose_name="URL главного изображения")
    in_stock = models.BooleanField(default=True, verbose_name="В наличии")
    category = models.CharField(max_length=200, null=True, blank=True, verbose_name="Категория")
    
    # Хранит специфичные атрибуты (размеры, бренд, параметры доставки и т.д.)
    extra_data = models.JSONField(
        default=dict, blank=True, verbose_name="Дополнительные данные"
    )

    scraped_at = models.DateTimeField(
        default=timezone.now, db_index=True,
        verbose_name="Дата и время скрапинга"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания записи")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления записи")

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["-scraped_at"]
        # Современный Django-way для уникальности (вместо unique_together)
        constraints = [
            models.UniqueConstraint(
                fields=["marketplace", "vendor_sku"],
                name="unique_marketplace_sku"
            )
        ]
        indexes = [
            models.Index(fields=["marketplace", "vendor_sku"], name="idx_marketplace_sku"),
            models.Index(fields=["-scraped_at"], name="idx_scraped_at_desc"),
        ]

    def __str__(self):
        return f"[{self.get_marketplace_display()}] {self.vendor_sku}: {self.title[:60]}..."


class SearchTarget(models.Model):
    """Целевые товары для парсинга. Управляется через Django Admin."""
    MARKETPLACE_CHOICES = [
        ('wb', 'Wildberries'),
        ('ozon', 'Ozon'),
    ]
    marketplace = models.CharField(max_length=10, choices=MARKETPLACE_CHOICES, db_index=True)
    article = models.CharField(max_length=100, verbose_name="Артикул / ID товара")
    search_query = models.CharField(
        max_length=255, 
        verbose_name="Поисковый запрос (для Ozon, WB игнорирует)", 
        blank=True, 
        null=True,
        help_text="Для Ozon: по какому запросу искать товар. Для WB можно оставить пустым."
    )

  
    priority = models.PositiveSmallIntegerField(default=10, verbose_name="Приоритет (1=высший)")
    is_active = models.BooleanField(default=True, verbose_name="Активен для парсинга")
    last_checked = models.DateTimeField(null=True, blank=True, verbose_name="Последняя проверка")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    
    class Meta:
        verbose_name = "Целевой товар"
        verbose_name_plural = "Целевые товары"
        ordering = ['priority', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['marketplace', 'article'], name='uniq_marketplace_article_target')
        ]

    def __str__(self):
        query_info = f" | '{self.search_query}'" if self.search_query else ""
        return f"[{self.get_marketplace_display()}] {self.article}{query_info} (P{self.priority})"
