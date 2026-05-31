"""
Management command для запуска парсера Wildberries.
Целевые артикулы и приоритеты загружаются из Admin → SearchTarget.
Использование:
    python manage.py run_wb [--force] [--limit N] [--test] [--export-only]
"""
import logging
from datetime import timedelta
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings

from apps.scrapers.models import ScrapeRun, SearchTarget, Marketplace
from apps.scrapers.wb_scraper import WildberriesSeleniumScraper
from apps.scrapers.storage import DataStorage, ProductData

logger = logging.getLogger('apps.scrapers')


class Command(BaseCommand):
    help = "Запуск парсера Wildberries на основе целей из Admin (SearchTarget)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Принудительный запуск, даже если есть активная сессия',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Ограничить количество обрабатываемых целей (для тестов)',
        )
        parser.add_argument(
            '--test',
            action='store_true',
            help='Тестовый режим: пропуск парсинга и сохранения в БД',
        )
        parser.add_argument(
            '--export-only',
            action='store_true',
            help='Только экспорт уже сохранённых в БД данных в CSV/Google Sheets',
        )
        parser.add_argument(
            '--export-hours',
            type=int,
            default=24,
            help='Период для экспорта (в часах), используется с --export-only',
        )

    def handle(self, *args, **options):
        force = options['force']
        limit = options['limit']
        test_mode = options['test']
        export_only = options['export_only']
        export_hours = options['export_hours']

        self.stdout.write(self.style.SUCCESS(f"🚀 Запуск WB scraper | limit={limit}, test={test_mode}"))

        # 1. Проверка на активную сессию (защита от параллельных запусков)
        active_run = ScrapeRun.objects.filter(
            marketplace=Marketplace.WILDBERRIES,
            status=ScrapeRun.Status.RUNNING,
            started_at__gte=timezone.now() - timedelta(hours=1)
        ).first()

        if active_run and not force:
            self.stdout.write(self.style.WARNING(
                f"⚠️ Активная сессия #{active_run.id} найдена. "
                "Дождитесь завершения или используйте --force."
            ))
            return

        if active_run and force:
            active_run.status = ScrapeRun.Status.FAILED
            active_run.error_message = "Принудительно завершена новым запуском (--force)"
            active_run.finished_at = timezone.now()
            active_run.save(update_fields=['status', 'error_message', 'finished_at'])
            logger.warning(f"Сессия WB #{active_run.id} завершена принудительно")

        # 2. Создание новой сессии
        scrape_run = ScrapeRun.objects.create(
            marketplace=Marketplace.WILDBERRIES,
            status=ScrapeRun.Status.RUNNING,
            started_at=timezone.now()
        )
        logger.info(f"Создана сессия скрапинга WB #{scrape_run.id}")

        try:
            if export_only:
                self._export_from_db(scrape_run, export_hours, test_mode)
            else:
                self._run_full_scrape(scrape_run, limit, test_mode)

            scrape_run.status = ScrapeRun.Status.SUCCESS
            self.stdout.write(self.style.SUCCESS("✅ WB scraper завершён успешно"))

        except KeyboardInterrupt:
            logger.warning("⚠️ Парсер прерван пользователем (Ctrl+C)")
            scrape_run.status = ScrapeRun.Status.FAILED
            scrape_run.error_message = "Прервано пользователем"
            raise CommandError("Прервано пользователем")

        except Exception as e:
            logger.exception(f"❌ Критическая ошибка в WB scraper: {e}")
            scrape_run.status = ScrapeRun.Status.FAILED
            scrape_run.error_message = f"{type(e).__name__}: {str(e)}"
            raise CommandError(f"Ошибка парсинга: {e}")

        finally:
            # 3. Финализируем сессию
            scrape_run.finished_at = timezone.now()
            scrape_run.save(update_fields=['status', 'error_message', 'finished_at', 'items_processed'])
            logger.info(f"Сессия WB #{scrape_run.id} завершена: {scrape_run.status}")

    def _run_full_scrape(self, scrape_run: ScrapeRun, limit: Optional[int], test_mode: bool):
        """Полный цикл: загрузка целей → парсинг → сохранение → обновление метрик."""
        
        # Загрузка активных целей из Admin
        targets_qs = SearchTarget.objects.filter(
            marketplace=Marketplace.WILDBERRIES,
            is_active=True
        ).order_by('priority', 'created_at')

        if limit:
            targets_qs = targets_qs[:limit]

        targets = list(targets_qs)
        if not targets:
            self.stdout.write(self.style.WARNING("⚠️ Нет активных целей в Admin. Добавьте через SearchTarget."))
            return

        articles = [t.article for t in targets]
        self.stdout.write(f"🎯 Найдено {len(articles)} целевых артикулов")

        if test_mode:
            self.stdout.write(self.style.WARNING("🧪 TEST MODE: пропуск парсинга и сохранения"))
            return

        # Инициализация парсера и хранилища
        scraper_config = getattr(settings, 'SCRAPER_CONFIG', {}).get('wb', {})
        scraper = WildberriesSeleniumScraper(config=scraper_config)
        
        storage_config = getattr(settings, 'SCRAPER_CONFIG', {})
        storage = DataStorage(config=storage_config, scrape_run=scrape_run)

        # Коллбэк прогресса (безопасен для systemd/cron логов)
        last_printed = 0
        def on_progress(current: int, total: int, success: int):
            nonlocal last_printed
            if current - last_printed >= 5 or current == total:  # печатаем каждые 5 товаров
                self.stdout.write(f"⏳ WB: {current}/{total} | найдено: {success}")
                last_printed = current

        # Запуск парсинга
        self.stdout.write("🔍 Начинаю парсинг Wildberries...")
        products = scraper.collect_multiple(articles, on_progress=on_progress)
        self.stdout.write(f"✅ Парсинг завершён. Найдено: {len(products)}/{len(articles)}")

        # Сохранение в БД + опциональный экспорт
        result = storage.save(products)
        scrape_run.items_processed = result['db_saved']

        # Обновление last_checked для найденных товаров
        if products:
            found_articles = {p.article for p in products}
            now = timezone.now()
            for t in targets:
                if t.article in found_articles:
                    t.last_checked = now
            SearchTarget.objects.bulk_update(targets, ['last_checked'])
            logger.info(f"Обновлено last_checked для {len(found_articles)} артикулов")

        self.stdout.write(f"💾 Сохранено в БД: {result['db_saved']}")
        if result.get('csv_path'):
            self.stdout.write(f"📄 CSV: {result['csv_path']}")
        if result.get('gs_success'):
            self.stdout.write("📊 Google Sheets: обновлено")

    def _export_from_db(self, scrape_run: ScrapeRun, hours: int, test_mode: bool):
        """Экспорт уже сохранённых в БД данных за последние N часов."""
        from apps.scrapers.models import Product
        
        cutoff = timezone.now() - timedelta(hours=hours)
        products_qs = Product.objects.filter(
            marketplace=Marketplace.WILDBERRIES,
            scraped_at__gte=cutoff
        ).order_by('-scraped_at')
        
        count = products_qs.count()
        self.stdout.write(f"📦 Найдено {count} товаров за последние {hours} ч. для экспорта")
        
        if count == 0 or test_mode:
            return

        # Конвертация queryset в ProductData для storage
        products = []
        for p in products_qs.iterator(chunk_size=100):
            products.append(ProductData(
                marketplace=p.marketplace,
                article=p.vendor_sku,
                name=p.title,
                price=p.price,
                old_price=p.old_price,
                availability=p.in_stock,
                rating=p.rating,
                reviews_count=p.review_count,
                url=p.url,
                collected_at=p.scraped_at,
                image_url=p.image_url,
                category=p.category,
                extra_data=p.extra_data or {},
            ))

        storage = DataStorage(config=getattr(settings, 'SCRAPER_CONFIG', {}), scrape_run=scrape_run)
        
        csv_path = storage.save_to_csv(products)
        gs_ok = storage.save_to_google_sheets(products)
        
        if csv_path:
            self.stdout.write(f"📄 CSV экспорт: {csv_path}")
        if gs_ok:
            self.stdout.write("📊 Google Sheets: обновлено")
        
        scrape_run.items_processed = count
