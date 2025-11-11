"""
Модуль для сохранения данных в CSV и Google Sheets
"""
import os
import csv
import logging
from typing import List
from datetime import datetime
import pandas as pd

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    logging.warning("gspread не установлен. Google Sheets функциональность недоступна")

logger = logging.getLogger(__name__)


class ProductData:
    """Класс для хранения данных о товаре (дублируем для импорта)"""
    def __init__(self, marketplace, article, name, price, old_price, availability,
                 rating, reviews_count, url, collected_at):
        self.marketplace = marketplace
        self.article = article
        self.name = name
        self.price = price
        self.old_price = old_price
        self.availability = availability
        self.rating = rating
        self.reviews_count = reviews_count
        self.url = url
        self.collected_at = collected_at


class DataStorage:
    """Класс для сохранения данных в различные форматы"""

    def __init__(self, config: dict):
        self.config = config
        self.storage_config = config.get('storage', {})

        # Инициализация Google Sheets
        self.gs_client = None
        if self.storage_config.get('google_sheets_enabled', False) and GSPREAD_AVAILABLE:
            self._init_google_sheets()

    def _init_google_sheets(self):
        """Инициализация подключения к Google Sheets"""
        try:
            credentials_path = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH', 'credentials.json')

            if not os.path.exists(credentials_path):
                logger.warning(f"Файл credentials.json не найден: {credentials_path}")
                return

            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]

            creds = Credentials.from_service_account_file(credentials_path, scopes=scope)
            self.gs_client = gspread.authorize(creds)
            logger.info("Подключение к Google Sheets установлено")
        except Exception as e:
            logger.error(f"Ошибка при подключении к Google Sheets: {e}")
            self.gs_client = None

    def save_to_csv(self, products: List) -> str:
        """Сохранить данные в CSV файл"""
        if not self.storage_config.get('csv_enabled', True):
            return None

        try:
            # Формирование имени файла с датой
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path_template = self.storage_config.get('csv_path', 'data/products_{date}.csv')
            file_path = csv_path_template.format(date=date_str)

            # Создание директории если не существует
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

            # Подготовка данных для сохранения
            rows = []
            for product in products:
                # Поддержка как объекта ProductData, так и словаря
                if hasattr(product, 'marketplace'):
                    # Это объект ProductData
                    rows.append({
                        'Дата сбора': product.collected_at,
                        'Маркетплейс': product.marketplace,
                        'Артикул': product.article,
                        'Название': product.name,
                        'Цена': product.price,
                        'Старая цена': product.old_price or '',
                        'Наличие': product.availability,
                        'Рейтинг': product.rating or '',
                        'Количество отзывов': product.reviews_count,
                        'Ссылка': product.url
                    })
                elif isinstance(product, dict):
                    # Это словарь
                    rows.append({
                        'Дата сбора': product.get('collected_at', ''),
                        'Маркетплейс': product.get('marketplace', ''),
                        'Артикул': product.get('article', ''),
                        'Название': product.get('name', ''),
                        'Цена': product.get('price', 0),
                        'Старая цена': product.get('old_price', '') or '',
                        'Наличие': product.get('availability', ''),
                        'Рейтинг': product.get('rating', '') or '',
                        'Количество отзывов': product.get('reviews_count', 0),
                        'Ссылка': product.get('url', '')
                    })

            if not rows:
                logger.warning("Нет данных для сохранения")
                return None

            # Сохранение в CSV
            df = pd.DataFrame(rows)
            df.to_csv(file_path, index=False, encoding='utf-8-sig')

            logger.info(f"Данные сохранены в CSV: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Ошибка при сохранении в CSV: {e}", exc_info=True)
            return None

    def save_to_google_sheets(self, products: List) -> bool:
        """Сохранить данные в Google Sheets"""
        # Детальное логирование ПЕРЕД блоком try-except
        logger.info(f"🔧 Начало сохранения в Google Sheets")
        logger.info(f"🔧 Количество продуктов для сохранения: {len(products)}")
        logger.info(f"🔧 Google Sheets enabled: {self.storage_config.get('google_sheets_enabled', False)}")
        logger.info(f"🔧 GSPREAD_AVAILABLE: {GSPREAD_AVAILABLE}")
        logger.info(f"🔧 GS client initialized: {self.gs_client is not None}")

        if not self.storage_config.get('google_sheets_enabled', False):
            logger.debug("Google Sheets отключен в конфигурации")
            return False

        if not self.gs_client:
            logger.warning("Google Sheets клиент не инициализирован")
            return False

        try:
            spreadsheet_id = self.storage_config.get('google_sheets_id', '')
            worksheet_name = self.storage_config.get('google_sheets_worksheet', 'Products')

            # Логирование перед операциями с таблицей
            logger.info(f"🔧 ID таблицы: {spreadsheet_id}")
            logger.info(f"🔧 Имя листа: {worksheet_name}")

            if not spreadsheet_id:
                logger.error("Не указан ID таблицы Google Sheets")
                return False

            # Открытие таблицы
            logger.info("🔧 Открываю таблицу...")
            spreadsheet = self.gs_client.open_by_key(spreadsheet_id)
            logger.info(f"🔧 Таблица открыта: {spreadsheet.title}")

            # Попытка открыть существующий лист или создание нового
            try:
                logger.info(f"🔧 Пытаюсь открыть лист: {worksheet_name}")
                worksheet = spreadsheet.worksheet(worksheet_name)
                logger.info(f"🔧 Лист найден: {worksheet.title}")
            except Exception as e:
                logger.warning(f"🔧 Лист не найден, создаю новый: {e}")
                try:
                    worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=10)
                    logger.info(f"🔧 Новый лист создан: {worksheet_name}")
                except Exception as create_error:
                    logger.error(f"🔧 Ошибка при создании листа: {create_error}")
                    return False

            # Подготовка данных
            headers = [
                'Дата сбора', 'Маркетплейс', 'Артикул', 'Название',
                'Цена', 'Старая цена', 'Наличие', 'Рейтинг',
                'Количество отзывов', 'Ссылка'
            ]

            rows = [headers]
            for product in products:
                # Поддержка как объекта ProductData, так и словаря
                if hasattr(product, 'marketplace'):
                    rows.append([
                        product.collected_at,
                        product.marketplace,
                        product.article,
                        product.name,
                        product.price,
                        product.old_price or '',
                        product.availability,
                        product.rating or '',
                        product.reviews_count,
                        product.url
                    ])
                elif isinstance(product, dict):
                    rows.append([
                        product.get('collected_at', ''),
                        product.get('marketplace', ''),
                        product.get('article', ''),
                        product.get('name', ''),
                        product.get('price', 0),
                        product.get('old_price', '') or '',
                        product.get('availability', ''),
                        product.get('rating', '') or '',
                        product.get('reviews_count', 0),
                        product.get('url', '')
                    ])

            logger.info(f"🔧 Подготовлено строк для записи: {len(rows)}")
            logger.info(f"🔧 Заголовки: {headers}")

            if len(rows) == 1:  # Только заголовки
                logger.warning("Нет данных для сохранения в Google Sheets")
                return False

            # Очистка листа и добавление новых данных
            logger.info("🔧 Очищаю лист...")
            worksheet.clear()
            logger.info("🔧 Добавляю данные...")
            worksheet.append_rows(rows)
            logger.info("🔧 Данные успешно добавлены")

            logger.info(f"✅ Данные сохранены в Google Sheets: {worksheet_name}")
            return True

        except Exception as e:
            # Логирование ошибок ВНУТРИ блока except
            logger.error(f"❌ Критическая ошибка при сохранении в Google Sheets: {e}", exc_info=True)
            logger.error(f"❌ Тип ошибки: {type(e).__name__}")
            return False

    def save(self, products: List):
        """Сохранить данные во все настроенные хранилища"""
        logger.info(f"💾 Начало сохранения {len(products)} продуктов")
        
        if not products:
            logger.warning("Список продуктов пуст, нечего сохранять")
            return

        if self.storage_config.get('csv_enabled', True):
            logger.info("💾 Сохраняю в CSV...")
            csv_result = self.save_to_csv(products)
            if csv_result:
                logger.info(f"✅ CSV сохранен: {csv_result}")
            else:
                logger.error("❌ Ошибка сохранения CSV")
        else:
            logger.info("⏭️ CSV отключен")

        if self.storage_config.get('google_sheets_enabled', False):
            logger.info("💾 Сохраняю в Google Sheets...")
            gs_result = self.save_to_google_sheets(products)
            if gs_result:
                logger.info("✅ Google Sheets сохранен успешно")
            else:
                logger.error("❌ Ошибка сохранения Google Sheets")
        else:
            logger.info("⏭️ Google Sheets отключен")
