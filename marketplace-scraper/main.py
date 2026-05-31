import json
import yaml
import logging
import os
from datetime import datetime
from ozon_selenium_scraper import OzonSeleniumScraper, save_to_json
from wb_selenium_scraper import WildberriesSeleniumScraper
from data_storage import DataStorage  # Добавьте этот импорт

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Main")

def load_config(config_path="config.yaml"):
    """Загрузка конфигурации"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки конфига: {e}")
        return {}

def get_target_articles(config):
    """Получение целевых артикулов из конфига"""
    target_articles = set()

    # Артикулы для Wildberries
    if config.get('products', {}).get('wildberries'):
        target_articles.update(config['products']['wildberries'])
        logger.info(f"🎯 Wildberries артикулы: {config['products']['wildberries']}")

    # Артикулы для Ozon
    if config.get('products', {}).get('ozon'):
        target_articles.update(config['products']['ozon'])
        logger.info(f"🎯 Ozon артикулы: {config['products']['ozon']}")

    return list(target_articles)

def ensure_data_directory():
    """Создает директорию data если не существует"""
    if not os.path.exists('data'):
        os.makedirs('data')
        logger.info("📁 Создана директория data")

def main():
    """Основная функция запуска"""
    logger.info("🚀 Запуск парсера маркетплейсов")

    # Создаем директорию data
    ensure_data_directory()

    # Загружаем конфиг
    config = load_config()
    
    # Инициализируем DataStorage
    storage = DataStorage(config)
    logger.info("💾 Инициализирован DataStorage")

    # Получаем артикулы из конфига
    target_articles = get_target_articles(config)
    if not target_articles:
        logger.error("❌ Не указаны целевые артикулы в конфиге")
        return

    logger.info(f"🎯 Всего целевых артикулов: {len(target_articles)}")

    all_products = []

    # Запуск Ozon парсера (только если есть Ozon артикулы)
    ozon_articles = config.get('products', {}).get('ozon', [])
    if ozon_articles and config.get('marketplaces', {}).get('ozon', {}).get('enabled', True):
        try:
            logger.info("🟠 Запуск Ozon парсера...")
            ozon_scraper = OzonSeleniumScraper(headless=True)
            ozon_products = ozon_scraper.search_target_products(ozon_articles)
            all_products.extend(ozon_products)
            logger.info(f"✅ Ozon: найдено {len(ozon_products)} товаров")
        except Exception as e:
            logger.error(f"❌ Ошибка Ozon парсера: {e}")
    else:
        logger.info("⏭️ Ozon парсер пропущен (нет артикулов или отключен в конфиге)")

    # Запуск Wildberries парсера (только если есть WB артикулы)
    wb_articles = config.get('products', {}).get('wildberries', [])
    if wb_articles and config.get('marketplaces', {}).get('wildberries', {}).get('enabled', True):
        try:
            logger.info("🟣 Запуск Wildberries парсера...")
            wb_scraper = WildberriesSeleniumScraper(headless=True)
            wb_products = []
            for article in wb_articles:
                logger.info(f"🔍 Обрабатываем артикул WB: {article}")
                product = wb_scraper.collect_product_data(article)
                if product:
                    wb_products.append(product.__dict__)
                    logger.info(f"✅ WB артикул {article} обработан успешно")
                else:
                    logger.warning(f"❌ WB артикул {article} не удалось обработать")

            all_products.extend(wb_products)
            logger.info(f"✅ Wildberries: найдено {len(wb_products)} товаров")
        except Exception as e:
            logger.error(f"❌ Ошибка Wildberries парсера: {e}")
    else:
        logger.info("⏭️ Wildberries парсер пропущен (нет артикулов или отключен в конфиге)")

    # Сохраняем все данные
    if all_products:
        # Сохраняем в JSON (существующий код)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        timestamp_file = f"data/products_{timestamp}.json"
        save_to_json(all_products, timestamp_file)
        logger.info(f"💾 Сохранено {len(all_products)} товаров в файл с timestamp: {timestamp_file}")

        latest_file = "data/products_latest.json"
        save_to_json(all_products, latest_file)
        logger.info(f"📄 Обновлен файл с последними данными: {latest_file}")

        # ✅ СОХРАНЯЕМ В CSV И GOOGLE SHEETS ЧЕРЕЗ DATASTORAGE
        storage.save(all_products)
        logger.info("✅ Данные сохранены через DataStorage")

        # Выводим краткую статистику
        ozon_count = len([p for p in all_products if p['marketplace'] == 'Ozon'])
        wb_count = len([p for p in all_products if p['marketplace'] == 'Wildberries'])
        logger.info(f"📊 Статистика: Ozon - {ozon_count}, Wildberries - {wb_count}")

        # Выводим результаты в консоль
        print("\n" + "="*80)
        print("🏆 РЕЗУЛЬТАТЫ СБОРА ДАННЫХ")
        print("="*80)
        for product in all_products:
            old_price_info = f" (было {product['old_price']})" if product.get('old_price') else ""
            rating_info = f", рейтинг: {product['rating']}" if product.get('rating') else ""
            reviews_info = f", отзывов: {product['reviews_count']}" if product.get('reviews_count') else ""
            availability_info = f", {product['availability']}" if product.get('availability') else ""

            print(f"🛒 {product['marketplace']} - {product['article']}")
            print(f"   📝 {product['name'][:70]}...")
            print(f"   💰 {product['price']} руб.{old_price_info}{rating_info}{reviews_info}{availability_info}")
            print()

    else:
        logger.warning("📭 Не найдено ни одного товара")

if __name__ == "__main__":
    main()
