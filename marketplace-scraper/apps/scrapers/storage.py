"""
Модуль для сохранения данных через Django ORM + опциональный экспорт в CSV/Google Sheets.
Основное хранилище — PostgreSQL через модели apps.scrapers.models.
"""
import os
import csv
import logging
from typing import List, Optional, Union
from datetime import datetime
from decimal import Decimal

import pandas as pd
from django.utils import timezone
from django.db import transaction
from django.conf import settings

# Optional Google Sheets dependencies
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

from apps.scrapers.models import Product, ScrapeRun, Marketplace as MarketplaceChoices

logger = logging.getLogger(__name__)


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def _format_datetime(dt: Optional[Union[datetime, str]]) -> str:
    """
    Конвертирует datetime или ISO-строку в строку формата 'YYYY-MM-DD HH:MM:SS' 
    в локальном часовом поясе (Москва).
    """
    if not dt:
        return ''
    
    # Если уже строка — пробуем распарсить
    if isinstance(dt, str):
        try:
            # Парсим ISO-формат (с заменой 'Z' на '+00:00' для совместимости)
            parsed = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            if parsed.tzinfo is not None:
                # Конвертируем aware datetime в локальный пояс
                return timezone.localtime(parsed).strftime('%Y-%m-%d %H:%M:%S')
            return parsed.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, AttributeError):
            # Если не удалось распарсить — возвращаем как есть
            return dt
    
    # Если datetime объект
    if dt.tzinfo is not None:
        # Конвертируем aware datetime в локальный часовой пояс
        local_dt = timezone.localtime(dt)
        return local_dt.strftime('%Y-%m-%d %H:%M:%S')
    return dt.strftime('%Y-%m-%d %H:%M:%S')

# =============================================================================
# КЛАССЫ ДАННЫХ
# =============================================================================

class ProductData:
    """
    Класс-адаптер для передачи данных из парсеров в storage.
    Совместим с вашим старым кодом (wb_selenium_scraper.py, ozon_selenium_scraper.py).
    """
    def __init__(
        self,
        marketplace: str,
        article: str,
        name: str,
        price: Union[float, Decimal, str],
        old_price: Optional[Union[float, Decimal, str]] = None,
        availability: bool = True,
        rating: Optional[float] = None,
        reviews_count: int = 0,
        url: str = "",
        collected_at: Optional[datetime] = None,
        # Дополнительные поля для гибкости
        image_url: Optional[str] = None,
        category: Optional[str] = None,
        extra_data: Optional[dict] = None,
    ):
        self.marketplace = marketplace  # 'wb' или 'ozon'
        self.article = article          # vendor_sku
        self.name = name
        self.price = Decimal(str(price)) if price is not None else None
        self.old_price = Decimal(str(old_price)) if old_price not in (None, '', 0) else None
        self.availability = availability
        self.rating = float(rating) if rating not in (None, '', 0) else None
        self.reviews_count = int(reviews_count or 0)
        self.url = url
        # 🔧 Используем timezone.now() по умолчанию для корректной работы с USE_TZ=True
        self.collected_at = collected_at if collected_at else timezone.now()
        self.image_url = image_url
        self.category = category
        self.extra_data = extra_data or {}

    def to_dict(self) -> dict:
        """Экспорт в dict для совместимости со старым кодом."""
        return {
            'marketplace': self.marketplace,
            'article': self.article,
            'name': self.name,
            'price': float(self.price) if self.price else None,
            'old_price': float(self.old_price) if self.old_price else None,
            'availability': self.availability,
            'rating': self.rating,
            'reviews_count': self.reviews_count,
            'url': self.url,
            'collected_at': self.collected_at.isoformat() if self.collected_at else None,
            'image_url': self.image_url,
            'category': self.category,
            'extra_data': self.extra_data,
        }


# =============================================================================
# ОСНОВНОЙ КЛАСС ХРАНИЛИЩА
# =============================================================================

class DataStorage:
    """
    Основной класс для сохранения данных.

    Логика:
    1. Все данные сохраняются в PostgreSQL через Django ORM (обязательно).
    2. Опционально: экспорт в CSV и/или Google Sheets (если включено в config).
    """

    def __init__(self, config: dict, scrape_run: Optional[ScrapeRun] = None):
        self.config = config
        self.storage_config = config.get('storage', {})
        self.scrape_run = scrape_run  # Опциональная ссылка на сессию для логирования

        # Инициализация Google Sheets (только если включено и есть зависимости)
        self.gs_client = None
        if self.storage_config.get('google_sheets_enabled', False) and GSPREAD_AVAILABLE:
            self._init_google_sheets()

    def _init_google_sheets(self):
        """Инициализация подключения к Google Sheets через Django settings."""
        try:
            # Используем путь из Django settings (загружен из .env)
            credentials_path = getattr(settings, 'GOOGLE_SHEETS_CREDENTIALS_PATH', 'credentials.json')
            credentials_path = str(credentials_path)  # На случай если это Path-объект

            if not os.path.exists(credentials_path):
                logger.warning(f"Файл учетных данных не найден: {credentials_path}")
                return

            scope = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_file(credentials_path, scopes=scope)
            self.gs_client = gspread.authorize(creds)
            logger.info("✅ Google Sheets клиент инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Google Sheets: {e}", exc_info=True)
            self.gs_client = None

    def _normalize_marketplace(self, value: str) -> str:
        """Приводит строку 'wb'/'wildberries' к значению из Marketplace.choices."""
        value = value.lower().strip()
        if value in ('wb', 'wildberries', 'wildberries.ru'):
            return MarketplaceChoices.WILDBERRIES
        elif value in ('ozon', 'ozon.ru'):
            return MarketplaceChoices.OZON
        # Если неизвестное значение — возвращаем как есть (Django валидация отловит)
        return value

    @transaction.atomic
    def save_to_db(self, products: List[Union[ProductData, dict]]) -> int:
        """
        Сохраняет список товаров в PostgreSQL через Django ORM.
        Использует update_or_create для избежания дубликатов.

        Returns:
            int: количество успешно сохранённых записей
        """
        if not products:
            logger.warning("📭 Пустой список товаров, ничего не сохраняю в БД")
            return 0

        saved_count = 0
        for item in products:
            try:
                # Нормализация входных данных
                if isinstance(item, ProductData):
                    data = item
                    marketplace = self._normalize_marketplace(data.marketplace)
                    vendor_sku = str(data.article).strip()
                    defaults = {
                        'title': data.name[:500],  # Ограничение по длине поля
                        'price': data.price,
                        'old_price': data.old_price,
                        'currency': 'RUB',
                        'rating': data.rating,
                        'review_count': data.reviews_count,
                        'url': data.url[:500],
                        'image_url': data.image_url[:500] if data.image_url else None,
                        'in_stock': data.availability,
                        'category': data.category[:200] if data.category else None,
                        'extra_data': data.extra_data,
                        'scraped_at': data.collected_at,  # Сохраняем как есть (aware datetime)
                    }
                elif isinstance(item, dict):
                    marketplace = self._normalize_marketplace(item.get('marketplace', ''))
                    vendor_sku = str(item.get('article', item.get('vendor_sku', ''))).strip()
                    defaults = {
                        'title': str(item.get('name', item.get('title', '')))[:500],
                        'price': Decimal(str(item['price'])) if item.get('price') not in (None, '', 0) else None,
                        'old_price': Decimal(str(item['old_price'])) if item.get('old_price') not in (None, '', 0) else None,
                        'currency': item.get('currency', 'RUB'),
                        'rating': float(item['rating']) if item.get('rating') not in (None, '', 0) else None,
                        'review_count': int(item.get('reviews_count', item.get('review_count', 0)) or 0),
                        'url': str(item.get('url', ''))[:500],
                        'image_url': str(item.get('image_url', ''))[:500] if item.get('image_url') else None,
                        'in_stock': item.get('availability', item.get('in_stock', True)),
                        'category': str(item.get('category', ''))[:200] if item.get('category') else None,
                        'extra_data': item.get('extra_data', {}),
                        'scraped_at': item.get('collected_at', timezone.now()),
                    }
                    # Создаём временный объект для совместимости с экспортёрами
                    data = ProductData(**{k: v for k, v in item.items() if hasattr(ProductData, '__init__') and k in ProductData.__init__.__code__.co_varnames})
                else:
                    logger.warning(f"⚠️ Неизвестный тип товара: {type(item)}, пропускаю")
                    continue

                if not vendor_sku:
                    logger.warning("⚠️ Пропущен товар без артикула (vendor_sku)")
                    continue

                # Сохранение в БД (upsert)
                obj, created = Product.objects.update_or_create(
                    marketplace=marketplace,
                    vendor_sku=vendor_sku,
                    defaults=defaults
                )
                saved_count += 1

                if created:
                    logger.debug(f"➕ Создан: [{marketplace}] {vendor_sku}")
                else:
                    logger.debug(f"✏️ Обновлён: [{marketplace}] {vendor_sku}")

            except Exception as e:
                logger.error(f"❌ Ошибка сохранения товара {item}: {e}", exc_info=True)
                # Не прерываем весь процесс из-за одного товара
                continue

        # Обновляем счётчик в сессии, если она передана
        if self.scrape_run:
            self.scrape_run.items_processed = Product.objects.filter(
                scraped_at__gte=self.scrape_run.started_at,
                marketplace=self.scrape_run.marketplace
            ).count()
            self.scrape_run.save(update_fields=['items_processed'])

        logger.info(f"💾 В БД сохранено {saved_count}/{len(products)} товаров")
        return saved_count

    
    def save_to_csv(self, products: List[Union[ProductData, dict]]) -> Optional[str]:
        """Экспорт в CSV (опционально, не заменяет БД)."""
        if not self.storage_config.get('csv_enabled', True):
            return None

        try:
            # 🔧 Используем timezone.now() для имени файла (локальное время)
            date_str = timezone.now().strftime("%Y%m%d_%H%M%S")
            csv_template = self.storage_config.get('csv_path', 'data/products_{date}.csv')
            file_path = csv_template.format(date=date_str)

            # Создаём директорию
            directory = os.path.dirname(file_path)
            if directory:
                os.makedirs(directory, exist_ok=True)

            # Конвертация для CSV — работаем напрямую с ProductData
            csv_rows = []
            for item in products:
                if isinstance(item, ProductData):
                    # 🔧 Прямой доступ к атрибутам (без to_dict())
                    csv_rows.append({
                        'Дата сбора': _format_datetime(item.collected_at),  # ✅ datetime объект
                        'Маркетплейс': item.marketplace,
                        'Артикул': item.article,
                        'Название': item.name,
                        'Цена': float(item.price) if item.price else '',
                        'Старая цена': float(item.old_price) if item.old_price else '',
                        'Наличие': 'Да' if item.availability else 'Нет',
                        'Рейтинг': item.rating,
                        'Отзывов': item.reviews_count,
                        'Ссылка': item.url,
                    })
                elif isinstance(item, dict):
                    # Для dict — используем _format_datetime (он теперь умеет парсить строки)
                    collected_at = item.get('collected_at')
                    csv_rows.append({
                        'Дата сбора': _format_datetime(collected_at),
                        'Маркетплейс': item.get('marketplace', ''),
                        'Артикул': item.get('article', item.get('vendor_sku', '')),
                        'Название': item.get('name', item.get('title', '')),
                        'Цена': float(item['price']) if item.get('price') else '',
                        'Старая цена': float(item['old_price']) if item.get('old_price') else '',
                        'Наличие': 'Да' if item.get('availability', True) else 'Нет',
                        'Рейтинг': item.get('rating', ''),
                        'Отзывов': item.get('reviews_count', item.get('review_count', 0)),
                        'Ссылка': item.get('url', ''),
                    })

            if not csv_rows:
                return None

            df = pd.DataFrame(csv_rows)
            df.to_csv(file_path, index=False, encoding='utf-8-sig')
            logger.info(f"📄 CSV экспорт: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"❌ Ошибка экспорта в CSV: {e}", exc_info=True)
            return None

    def save_to_google_sheets(self, products: List[ProductData]) -> bool:
        """
        Экспорт в Google Sheets с ЯВНОЙ адресацией колонок A–J.
        Игнорирует «мусор» в дальних колонках листа.
        Время конвертируется в локальный часовой пояс (Москва).
        """
        import os
        from decimal import Decimal

        gs_enabled = os.getenv('GOOGLE_SHEETS_ENABLED', 'False').lower() == 'true'
        gs_spreadsheet_id = os.getenv('GOOGLE_SHEETS_SPREADSHEET_ID', '').strip()
        gs_credentials_path = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH', 'credentials.json').strip()
        gs_worksheet_name = os.getenv('GOOGLE_SHEETS_WORKSHEET', 'Data').strip()

        if not gs_enabled or not gs_spreadsheet_id or not os.path.exists(gs_credentials_path):
            return False

        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            creds = Credentials.from_service_account_file(gs_credentials_path, scopes=scope)
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(gs_spreadsheet_id)

            # Получаем или создаём лист
            try:
                worksheet = spreadsheet.worksheet(gs_worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(title=gs_worksheet_name, rows=1000, cols=10)
                # Заголовки строго в A1:J1
                worksheet.update('A1:J1', [['Дата сбора', 'Маркетплейс', 'Артикул', 'Название', 'Цена', 'Старая цена', 'Наличие', 'Рейтинг', 'Отзывов', 'Ссылка']])
                logger.info(f"📄 Создан лист '{gs_worksheet_name}' с заголовками A1:J1")

            # Конвертер значений
            def fmt(val):
                if val is None: return ''
                if isinstance(val, bool): return 'Yes' if val else 'No'
                if isinstance(val, Decimal): return float(val)
                if isinstance(val, datetime): return _format_datetime(val)  # 🔧 Конвертация времени
                return str(val)

            # 🔴 Определяем следующую свободную строку ТОЛЬКО в колонках A–J
            existing_data = worksheet.get('A:J')

            next_row = len(existing_data) + 1
            if next_row == 1:  # Если лист пустой — добавляем заголовки
                worksheet.update('A1:J1', [['Дата сбора', 'Маркетплейс', 'Артикул', 'Название', 'Цена', 'Старая цена', 'Наличие', 'Рейтинг', 'Отзывов', 'Ссылка']])
                next_row = 2

            # 🔴 Подготовка и запись данных с ЯВНЫМ указанием диапазона
            rows_to_write = []
            for p in products:
                mp = {'wb': 'Wildberries', 'ozon': 'Ozon'}.get(str(p.marketplace or '').lower().strip(), str(p.marketplace or 'Unknown').strip())
                if not mp: mp = 'Unknown'

                row = [
                    _format_datetime(p.collected_at),  # 🔧 A: Дата в локальном поясе
                    mp,                                # B
                    fmt(p.article),                    # C
                    fmt(p.name[:300] if p.name else ''),  # D
                    fmt(p.price),                      # E
                    fmt(p.old_price),                  # F
                    fmt(p.availability),               # G
                    fmt(p.rating),                     # H
                    fmt(p.reviews_count or 0),         # I
                    fmt(p.url if p.url else ''),       # J
                ]
                rows_to_write.append(row)

            if rows_to_write:
                # 🔴 Явно указываем диапазон: например, A2:J2, A3:J3 и т.д.
                for i, row in enumerate(rows_to_write, start=next_row):
                    range_name = f'A{i}:J{i}'
                    worksheet.update(range_name, [row], value_input_option='RAW')
                    logger.info(f"📊 GS: записано в {range_name} | {mp} | {p.article}")

                logger.info(f"✅ Google Sheets: записано {len(rows_to_write)} строк в '{gs_worksheet_name}'")
                return True

            logger.debug("📊 Google Sheets: нет данных для записи")
            return True

        except gspread.exceptions.APIError as e:
            logger.error(f"❌ Google Sheets API ошибка: {e}", exc_info=True)
            if hasattr(e, 'response'):
                logger.error(f"📄 Ответ API: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"❌ Google Sheets ошибка: {type(e).__name__}: {e}", exc_info=True)
            return False

    def save(self, products: List[Union[ProductData, dict]]) -> dict:
        """
        Основной метод сохранения.
        1. Всегда сохраняет в БД (Django ORM).
        2. Опционально экспортирует в CSV и/или Google Sheets.

        Returns:
            dict: статистика операций
        """
        result = {
            'db_saved': 0,
            'csv_path': None,
            'gs_success': False,
        }

        if not products:
            logger.warning("📭 Пустой список, сохранение пропущено")
            return result

        logger.info(f"🚀 Начало сохранения {len(products)} товаров")

        # 1. Основной этап: БД (в транзакции)
        result['db_saved'] = self.save_to_db(products)

        # 2. Опциональные экспорты
        if self.storage_config.get('csv_enabled', True):
            result['csv_path'] = self.save_to_csv(products)

        if self.storage_config.get('google_sheets_enabled', False):
            result['gs_success'] = self.save_to_google_sheets(products)

        logger.info(f"✅ Сохранение завершено: БД={result['db_saved']}, CSV={result['csv_path'] is not None}, GS={result['gs_success']}")
        return result
