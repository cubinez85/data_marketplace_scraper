"""
Management command для запуска парсера Ozon.
Целевые артикулы и поисковые запросы загружаются из Admin → SearchTarget.
Автоматически группирует товары по search_query для оптимизации работы браузера.

Использование:
    python manage.py run_ozon [--force] [--limit N] [--test] [--export-only]
"""
import logging
from datetime import timedelta
from typing import Optional
from itertools import groupby
from operator import attrgetter

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings

from apps.scrapers.models import ScrapeRun, SearchTarget, Marketplace
from apps.scrapers.ozon_scraper import OzonSeleniumScraper
from apps.scrapers.storage import DataStorage, ProductData

logger = logging.getLogger('apps.scrapers')


class Command(BaseCommand):
    help = "Запуск парсера Ozon на основе целей из Admin (SearchTarget)"

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

        self.stdout.write(self.style.SUCCESS(f"🚀 Запуск Ozon scraper | limit={limit}, test={test_mode}"))

        # 1. Проверка на активную сессию
        active_run = ScrapeRun.objects.filter(
            marketplace=Marketplace.OZON,
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
            logger.warning(f"Сессия Ozon #{active_run.id} завершена принудительно")

        # 2. Создание новой сессии
        scrape_run = ScrapeRun.objects.create(
            marketplace=Marketplace.OZON,
            status=ScrapeRun.Status.RUNNING,
            started_at=timezone.now()
        )
        logger.info(f"Создана сессия скрапинга Ozon #{scrape_run.id}")

        try:
            if export_only:
                self._export_from_db(scrape_run, export_hours, test_mode)
            else:
                self._run_full_scrape(scrape_run, limit, test_mode)

            scrape_run.status = ScrapeRun.Status.SUCCESS
            self.stdout.write(self.style.SUCCESS("✅ Ozon scraper завершён успешно"))

        except KeyboardInterrupt:
            logger.warning("⚠️ Парсер прерван пользователем (Ctrl+C)")
            scrape_run.status = ScrapeRun.Status.FAILED
            scrape_run.error_message = "Прервано пользователем"
            raise CommandError("Прервано пользователем")

        except Exception as e:
            logger.exception(f"❌ Критическая ошибка в Ozon scraper: {e}")
            scrape_run.status = ScrapeRun.Status.FAILED
            scrape_run.error_message = f"{type(e).__name__}: {str(e)}"
            raise CommandError(f"Ошибка парсинга: {e}")

        finally:
            # 3. Финализируем сессию
            scrape_run.finished_at = timezone.now()
            scrape_run.save(update_fields=['status', 'error_message', 'finished_at', 'items_processed'])
            logger.info(f"Сессия Ozon #{scrape_run.id} завершена: {scrape_run.status}")

    def _run_full_scrape(self, scrape_run: ScrapeRun, limit: Optional[int], test_mode: bool):
        """Полный цикл: загрузка целей → группировка по query → парсинг → сохранение."""
        
        # Загрузка активных целей из Admin
        targets_qs = SearchTarget.objects.filter(
            marketplace=Marketplace.OZON,
            is_active=True
        ).order_by('priority', 'search_query', 'created_at')

        if limit:
            targets_qs = targets_qs[:limit]

        targets = list(targets_qs)
        if not targets:
            self.stdout.write(self.style.WARNING("⚠️ Нет активных целей Ozon в Admin. Добавьте через SearchTarget."))
            return

        self.stdout.write(f"🎯 Найдено {len(targets)} целевых артикулов")

        if test_mode:
            self.stdout.write(self.style.WARNING("🧪 TEST MODE: пропуск парсинга и сохранения"))
            return

        # Инициализация конфигов и хранилища
        scraper_config = getattr(settings, 'SCRAPER_CONFIG', {}).get('ozon', {})
        storage_config = getattr(settings, 'SCRAPER_CONFIG', {})
        storage = DataStorage(config=storage_config, scrape_run=scrape_run)

        # Группировка целей по search_query (требует сортировки по тому же ключу)
        sorted_targets = sorted(targets, key=attrgetter('search_query'))
        grouped_queries = groupby(sorted_targets, key=attrgetter('search_query'))

        total_saved = 0
        group_index = 0
        last_printed = 0

        for query, group_iter in grouped_queries:
            group_items = list(group_iter)
            query_str = (query or '').strip()
            
            # Ozon не может работать без поискового запроса
            if not query_str:
                self.stdout.write(self.style.ERROR(f"❌ Пропущена группа артикулов с пустым search_query"))
                for t in group_items:
                    logger.warning(f"SearchTarget ID={t.id} (article={t.article}) имеет пустой search_query")
                continue

            group_index += 1
            articles = [t.article for t in group_items]
            self.stdout.write(f"🔍 Группа {group_index}: Запрос '{query_str}' → {len(articles)} артикулов")

            # Инициализация скрапера для каждой группы (чистый state)
            scraper = OzonSeleniumScraper(config=scraper_config)

            def on_progress(current: int, total: int, found: int):
                nonlocal last_printed
                if current - last_printed >= 5 or current == total:
                    self.stdout.write(f"⏳ Ozon ({query_str}): {current}/{total} | найдено: {found}")
                    last_printed = current

            try:
                products = scraper.search_target_products(
                    target_articles=articles,
                    search_query=query_str,
                    on_progress=on_progress
                )
                
                if products:
                    result = storage.save(products)
                    total_saved += result['db_saved']
                    
                    self.stdout.write(f"✅ Группа '{query_str}' завершена. Найдено: {len(products)}/{len(articles)}")
                    
                    # Обновляем last_checked для найденных товаров
                    found_articles = {p.article for p in products}
                    now = timezone.now()
                    for t in group_items:
                        if t.article in found_articles:
                            t.last_checked = now
                    SearchTarget.objects.bulk_update(group_items, ['last_checked'])
                else:
                    self.stdout.write(self.style.WARNING(f"⚠️ Группа '{query_str}' не вернула результатов"))

            except ValueError as e:
                # Поймаем ошибку скрапера о пустом query_str, если проверка выше не сработала
                logger.error(f"❌ Ошибка в группе '{query_str}': {e}")
                self.stdout.write(self.style.ERROR(f"❌ Ошибка: {e}"))
            except Exception as e:
                logger.exception(f"❌ Критическая ошибка в группе '{query_str}': {e}")
                self.stdout.write(self.style.ERROR(f"❌ Ошибка группы: {e}"))

            # Небольшая пауза между группами запросов (вежливость к серверу)
            if group_index < len(sorted(targets, key=lambda t: t.search_query)):
                self.stdout.write("⏳ Пауза 5 сек перед следующим запросом...")
                import time; time.sleep(5)

        scrape_run.items_processed = total_saved
        self.stdout.write(f"💾 Итого сохранено в БД: {total_saved}")
        
        # Выводим итоги экспорта из последнего результата storage
        if hasattr(storage, '_last_export_result'):
            res = storage._last_export_result
            if res.get('csv_path'): self.stdout.write(f"📄 CSV: {res['csv_path']}")
            if res.get('gs_success'): self.stdout.write("📊 Google Sheets: обновлено")

    def _export_from_db(self, scrape_run: ScrapeRun, hours: int, test_mode: bool):
        """Экспорт уже сохранённых в БД данных за последние N часов."""
        from apps.scrapers.models import Product
        
        cutoff = timezone.now() - timedelta(hours=hours)
        products_qs = Product.objects.filter(
            marketplace=Marketplace.OZON,
            scraped_at__gte=cutoff
        ).order_by('-scraped_at')
        
        count = products_qs.count()
        self.stdout.write(f"📦 Найдено {count} товаров за последние {hours} ч. для экспорта")
        
        if count == 0 or test_mode:
            return

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
