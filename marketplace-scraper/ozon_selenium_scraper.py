# ozon_selenium_scraper.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth
import pandas as pd
import time
import re
import random
import os
import json
import logging
from datetime import datetime
from typing import Optional

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Ozon_Scraper")

def setup_driver():
    """Настройка драйвера"""
    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--start-maximized')
    options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=options)

    stealth(driver,
            languages=["ru-RU", "ru"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
            )

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: function() {return undefined;}})")

    return driver

def human_like_delay(min_seconds=1, max_seconds=3):
    """Случайная задержка"""
    time.sleep(random.uniform(min_seconds, max_seconds))

def scroll_page(driver, max_scrolls=8):
    """Прокрутка страницы поиска"""
    logger.info("📜 Начинаем прокрутку страницы поиска...")

    for scroll in range(max_scrolls):
        scroll_height = random.randint(800, 1200)
        driver.execute_script(f"window.scrollBy(0, {scroll_height});")
        logger.debug(f"📜 Прокрутка {scroll + 1}/{max_scrolls}")

        human_like_delay(2, 3)

        # Проверяем достигли ли конца
        new_height = driver.execute_script("return document.body.scrollHeight")
        current_pos = driver.execute_script("return window.pageYOffset + window.innerHeight")

        if current_pos >= new_height - 100:
            logger.info("🛑 Достигнут конец страницы")
            break

def find_all_products_safe(driver):
    """Безопасный поиск всех карточек товаров с обновлением элементов"""
    logger.info("🔍 Ищем все товары на странице поиска...")

    # Ждем загрузки товаров
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='tile'], article[class*='tile']"))
        )
    except:
        logger.warning("⏳ Товары загружаются медленно...")

    # Собираем данные сразу, без хранения ссылок на элементы
    products_data = []
    seen_articles = set()  # Для отслеживания уникальных артикулов

    # Селекторы для карточек товаров
    selectors = [
        "div[class*='tile-root']",
        "article[class*='tile-root']",
        "div[class*='widget-search-result'] div[class*='tile']",
        "div[class*='search-result'] div[class*='tile']",
        "div[class*='tile']",
        "article[class*='tile']",
        "div[class*='card']"
    ]

    for selector in selectors:
        try:
            # Каждый раз находим элементы заново
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                try:
                    # Сразу извлекаем все нужные данные из элемента
                    product_info = extract_product_info_immediately(element, driver)
                    if product_info:
                        # Проверяем на дубликаты по артикулу
                        if product_info['article'] not in seen_articles:
                            products_data.append(product_info)
                            seen_articles.add(product_info['article'])
                            logger.debug(f"📦 Добавлен товар: {product_info['article']}")
                        else:
                            logger.debug(f"🔄 Пропущен дубликат: {product_info['article']}")
                except Exception as e:
                    continue

        except Exception as e:
            logger.debug(f"Ошибка при поиске по селектору {selector}: {e}")
            continue

    logger.info(f"📦 Собрано уникальных товаров: {len(products_data)}")
    return products_data

def extract_product_info_immediately(element, driver):
    """Немедленное извлечение всей информации из элемента"""
    try:
        # Получаем ссылку на товар
        link_selectors = [
            "a[href*='/product/']",
            "a[class*='tile-link']",
            "a[class*='card-link']"
        ]

        product_url = None
        for selector in link_selectors:
            try:
                link_element = element.find_element(By.CSS_SELECTOR, selector)
                product_url = link_element.get_attribute("href")
                if product_url:
                    break
            except:
                continue

        if not product_url:
            return None

        # Извлекаем артикул из URL
        article = extract_article_from_url(product_url)
        if not article:
            return None

        # Извлекаем название
        name = extract_product_name(element)
        if not name:
            return None

        # Извлекаем цену
        price = extract_accurate_price(element, driver)
        if not price or price < 1000:
            return None

        # Извлекаем дополнительные данные
        rating = extract_rating(element)
        reviews_count = extract_reviews_count(element)
        old_price = extract_old_price(element)

        return {
            'marketplace': 'Ozon',
            'article': article,
            'name': name,
            'price': price,
            'old_price': old_price,
            'rating': rating,
            'reviews_count': reviews_count,
            'url': product_url,
            'collected_at': datetime.now().isoformat()
        }

    except Exception as e:
        return None

def extract_article_from_url(url):
    """Извлечение артикула из URL товара"""
    patterns = [
        r'/product/[^/]*?(\d+)/',
        r'--(\d+)/?$',
        r'/(\d+)/?$'
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""

def extract_accurate_price(element, driver):
    """Точное извлечение цены"""
    try:
        price_selectors = [
            "span[class*='price']",
            "div[class*='price']",
            "span[class*='tsHeadline']",
            "div[class*='tsHeadline']",
            "span[class*='cost']",
            "div[class*='cost']",
            ".c311-a1", ".a0c1", ".a1v9",
            "[data-widget*='price']"
        ]

        for selector in price_selectors:
            try:
                price_elements = element.find_elements(By.CSS_SELECTOR, selector)
                for price_element in price_elements:
                    price_text = price_element.text.strip()
                    if price_text:
                        clean_text = re.sub(r'[^\d\s]', '', price_text)
                        clean_text = re.sub(r'\s+', '', clean_text)

                        if clean_text and len(clean_text) >= 3:
                            price = int(clean_text)
                            if 1000 <= price <= 100000:
                                return price
            except:
                continue

        # Альтернативные методы поиска цены
        element_text = element.text
        price_patterns = [
            r'(\d{1,3}[ \ ]?\d{3}[ \ ]?\d{0,3})[ \ ]?₽?',
            r'₽[ \ ]*(\d{1,3}[ \ ]?\d{3}[ \ ]?\d{0,3})'
        ]

        for pattern in price_patterns:
            price_matches = re.findall(pattern, element_text)
            for match in price_matches:
                clean_price = re.sub(r'[^\d]', '', str(match))
                if clean_price:
                    price = int(clean_price)
                    if 1000 <= price <= 100000:
                        return price

        return None

    except Exception as e:
        return None

def extract_product_name(element):
    """Извлечение названия товара"""
    try:
        title_selectors = [
            "span[class*='tsBody']",
            "a[class*='title']",
            "span[class*='title']",
            "div[class*='title']",
            "h3", "h4",
            ".a5-a",
            "[class*='tile-title']"
        ]

        for selector in title_selectors:
            try:
                title_elements = element.find_elements(By.CSS_SELECTOR, selector)
                for title_element in title_elements:
                    title_text = title_element.text.strip()
                    if title_text and len(title_text) > 10:
                        return title_text
            except:
                continue

        # Fallback
        try:
            text = element.text.split('\n')[0]
            if text and len(text) > 10:
                return text
        except:
            pass

        return None

    except Exception as e:
        return None

def extract_rating(element):
    """Извлечение рейтинга"""
    try:
        rating_selectors = [
            "span[class*='rating']",
            "div[class*='rating']",
            "[class*='star-rate']"
        ]

        for selector in rating_selectors:
            try:
                rating_elements = element.find_elements(By.CSS_SELECTOR, selector)
                for rating_elem in rating_elements:
                    rating_text = rating_elem.text.strip()
                    if rating_text:
                        match = re.search(r'(\d+[.,]\d+)', rating_text)
                        if match:
                            return float(match.group(1).replace(',', '.'))
            except:
                continue
        return None
    except:
        return None

def extract_reviews_count(element):
    """Извлечение количества отзывов"""
    try:
        reviews_selectors = [
            "span[class*='review']",
            "div[class*='review']",
            "[class*='review-count']"
        ]

        for selector in reviews_selectors:
            try:
                reviews_elements = element.find_elements(By.CSS_SELECTOR, selector)
                for reviews_elem in reviews_elements:
                    reviews_text = reviews_elem.text.strip()
                    if reviews_text:
                        match = re.search(r'(\d+)', reviews_text)
                        if match:
                            return int(match.group(1))
            except:
                continue
        return 0
    except:
        return 0

def extract_old_price(element):
    """Извлечение старой цены"""
    try:
        old_price_selectors = [
            "span[class*='old-price']",
            "div[class*='old-price']",
            "s[class*='price']"
        ]

        for selector in old_price_selectors:
            try:
                old_price_elements = element.find_elements(By.CSS_SELECTOR, selector)
                for old_elem in old_price_elements:
                    old_text = old_elem.text.strip()
                    if old_text:
                        clean_text = re.sub(r'[^\d\s]', '', old_text)
                        clean_text = re.sub(r'\s+', '', clean_text)

                        if clean_text and len(clean_text) >= 3:
                            old_price = int(clean_text)
                            if old_price > 1000:
                                return old_price
            except:
                continue
        return None
    except:
        return None

class OzonSeleniumScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless

    def search_target_products(self, target_articles):
        """Поиск целевых товаров по артикулам"""
        driver = setup_driver()
        found_products = []
        target_articles_set = set(target_articles)

        try:
            # URL поиска с конкретным запросом
            search_url = "https://www.ozon.ru/search/?from_global=true&text=умный+телевизор+32+с+голосовым+управлением+os+salute+tv"

            logger.info(f"🌐 Открываем страницу поиска: {search_url}")
            driver.get(search_url)
            time.sleep(10)

            # Прокрутка для загрузки всех товаров
            scroll_page(driver, max_scrolls=10)

            # Поиск всех товаров на странице (безопасный метод)
            all_products_data = find_all_products_safe(driver)

            logger.info(f"🔍 Ищем целевые артикулы: {target_articles}")
            logger.info(f"📦 Всего уникальных товаров на странице: {len(all_products_data)}")

            # Фильтруем по целевым артикулам
            for product_data in all_products_data:
                if product_data['article'] in target_articles_set:
                    found_products.append(product_data)
                    logger.info(f"✅ НАЙДЕН ЦЕЛЕВОЙ ТОВАР: {product_data['article']} - {product_data['name'][:50]}...")

            # Удаляем дубликаты (на всякий случай)
            found_products = self.remove_duplicates(found_products)

            logger.info(f"📊 Поиск завершен. Найдено целевых товаров: {len(found_products)}/{len(target_articles)}")

            # Если не все найдены, выводим какие именно
            found_articles = {p['article'] for p in found_products}
            missing_articles = target_articles_set - found_articles
            if missing_articles:
                logger.warning(f"❌ Не найдены артикулы: {missing_articles}")

        except Exception as e:
            logger.error(f"🚨 Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()
        finally:
            driver.quit()

        return found_products

    def remove_duplicates(self, products):
        """Удаление дубликатов из списка товаров"""
        if not products:
            return []

        logger.info("🧹 Удаляем дубликаты...")
        logger.info(f"📊 До удаления дубликатов: {len(products)} товаров")

        # Удаляем дубликаты по артикулу (самый надежный способ)
        unique_products = []
        seen_articles = set()

        for product in products:
            article = product['article']
            if article not in seen_articles:
                unique_products.append(product)
                seen_articles.add(article)
            else:
                logger.debug(f"🗑️ Удален дубликат: {article}")

        logger.info(f"📊 После удаления дубликатов: {len(unique_products)} товаров")
        return unique_products

def save_to_json(data, filename="data/products_latest.json"):
    """Сохранение данных в JSON файл в директории data"""
    try:
        # Создаем директорию data если нужно
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Читаем существующие данные только для latest файла
        existing_data = []
        if os.path.exists(filename) and "latest" in filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"⚠️ Файл {filename} поврежден, создаем новый")
                existing_data = []
        
        # Для файлов с timestamp просто перезаписываем
        if "latest" in filename:
            all_data = existing_data + data
        else:
            all_data = data
        
        # Удаляем дубликаты по артикулу и маркетплейсу
        unique_data = []
        seen = set()
        
        for item in all_data:
            key = (str(item['article']), item['marketplace'])
            if key not in seen:
                unique_data.append(item)
                seen.add(key)
        
        # Сохраняем
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(unique_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Сохранено {len(data)} товаров в {filename} (всего уникальных: {len(unique_data)})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения в JSON: {e}")
        return False

if __name__ == "__main__":
    # Пример использования
    scraper = OzonSeleniumScraper()
    
    # Артикулы для поиска (должны приходить из конфига через main.py)
    target_articles = ["1955609657", "2573828081"]
    
    logger.info("🚀 Запуск парсера Ozon")
    products = scraper.search_target_products(target_articles)
    
    if products:
        save_to_json(products)
        logger.info(f"✅ Найдено товаров: {len(products)}")
    else:
        logger.warning("❌ Товары не найдены")
