from django.contrib import admin
from django.shortcuts import redirect
from django.contrib import messages
from .models import SearchTarget, Product, ScrapeRun
from .admin_actions import run_scraper_async


@admin.register(SearchTarget)
class SearchTargetAdmin(admin.ModelAdmin):
    list_display = ('marketplace', 'article', 'search_query', 'priority', 'is_active', 'last_checked')
    list_filter = ('marketplace', 'is_active', 'priority')
    search_fields = ('article', 'search_query')
    list_editable = ('priority', 'search_query')
    ordering = ('priority', 'created_at')
    actions = ['activate_selected', 'deactivate_selected']
    exclude = ('search_category',)

    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'✅ Активировано {updated} записей')
    activate_selected.short_description = "Активировать выбранные"

    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'️ Деактивировано {updated} записей')
    deactivate_selected.short_description = "Деактивировать выбранные"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('article', 'title', 'marketplace', 'price', 'in_stock', 'scraped_at')
    list_filter = ('marketplace', 'in_stock', 'scraped_at')
    search_fields = ('article', 'title', 'category')
    readonly_fields = ('marketplace', 'article', 'title', 'price', 'url', 'scraped_at')
    
    def has_add_permission(self, request):
        return False


@admin.register(ScrapeRun)
class ScrapeRunAdmin(admin.ModelAdmin):
    """Безопасная админка истории запусков."""
    
    list_display = ('id', 'marketplace', 'status', 'started_at', 'finished_at', 'items_processed')
    list_filter = ('marketplace', 'status', 'started_at')
    readonly_fields = ('marketplace', 'status', 'started_at', 'finished_at', 'items_processed', 'error_message')
    ordering = ('-started_at',)
    
    # ✅ ACTIONS: строго 3 аргумента (self, request, queryset)
    actions = ['run_ozon_action', 'run_wb_action']

    def run_ozon_action(self, request, queryset):
        run_scraper_async('ozon', request)
        self.message_user(request, "🚀 Ozon запущен в фоновом режиме. Обновите страницу через 1-2 мин.")
        return redirect('.')
    run_ozon_action.short_description = "🟠 Запустить парсер Ozon сейчас"

    def run_wb_action(self, request, queryset):
        run_scraper_async('wb', request)
        self.message_user(request, "🚀 Wildberries запущен в фоновом режиме. Обновите страницу через 1-2 мин.")
        return redirect('.')
    run_wb_action.short_description = "🟢 Запустить парсер WB сейчас"

    def has_add_permission(self, request):
        return False
