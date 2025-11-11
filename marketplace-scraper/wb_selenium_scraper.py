# wb_selenium_scraper.py
import time
import random
import re
import logging
import os
import json
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth
import pandas as pd

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("WB_Scraper")

@dataclass
class ProductData:
    marketplace: str
    article: str
    name: str
    price: float
    old_price: Optional[float]
    availability: str
    rating: Optional[float]
    reviews_count: int
    url: str
    collected_at: str

def setup_driver(headless: bool = True):
    """Настройка драйвера для Wildberries (на основе рабочего кода)"""
    options = Options()

    # Базовые настройки
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--start-maximized')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--disable-notifications')

    if headless:
        options.add_argument('--headless=new')

    # User-agent для Wildberries
    options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    options.add_argument('--accept-lang=ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7')

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=options)

    # Применяем stealth режим
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
    """Случайная задержка между действиями"""
    time.sleep(random.uniform(min_seconds, max_seconds))

def wait_for_page_load(driver, timeout=10):
    """Ожидание загрузки страницы"""
    WebDriverWait(driver, timeout).until(
        lambda driver: driver.execute_script('return document.readyState') == 'complete'
    )

def close_wildberries_popups(driver):
    """Закрытие всплывающих окон на Wildberries"""
    try:
        time.sleep(2)

        # Закрываем куки
        try:
            cookie_btn = driver.find_element(By.CSS_SELECTOR,
                                             '.cookie-notification__button, .cookies__button, [data-wba-header-name*="Cookie"]')
            if cookie_btn.is_displayed():
                cookie_btn.click()
                time.sleep(1)
        except:
            pass

        # Закрываем геолокацию
        try:
            geo_btn = driver.find_element(By.CSS_SELECTOR,
                                          '.geo__close, .location__close, [data-wba-header-name*="Location"]')
            if geo_btn.is_displayed():
                geo_btn.click()
                time.sleep(1)
        except:
            pass

        # Закрываем другие попапы
        close_selectors = [
            'button[aria-label*="Закрыть"]',
            '.popup__close',
            '.j-close',
            '.modal__close'
        ]

        for selector in close_selectors:
            try:
                close_btns = driver.find_elements(By.CSS_SELECTOR, selector)
                for btn in close_btns:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(0.5)
            except:
                pass

    except Exception as e:
        logger.debug(f"Ошибка при закрытии попапов: {e}")

def extract_price_from_text(text: str) -> Optional[float]:
    """Извлечение цены из текста"""
    try:
        if not text:
            return None
            
        # Удаляем все нецифровые символы кроме точек, запятых и пробелов
        clean_text = re.sub(r'[^\d\s,.]', '', text.strip())
        # Убираем пробелы (разделители тысяч)
        clean_text = clean_text.replace(' ', '')
        # Заменяем запятую на точку для float преобразования
        clean_text = clean_text.replace(',', '.')
        
        if clean_text:
            price = float(clean_text)
            # Проверяем разумный диапазон цен (от 10 рублей до 1 млн)
            if 10 <= price <= 1000000:
                return price
    except (ValueError, TypeError):
        pass
    return None

def clean_product_name(name):
    """Очищает название товара от лишних символов"""
    if not name:
        return "Неизвестный товар"

    # Удаляем лишние пробелы
    name = re.sub(r'\s+', ' ', name).strip()

    # Удаляем цену в конце названия
    name = re.sub(r'\d{1,3}[ \ ]?\d{3}[ \ ]?\d{0,3}[ \ ]?₽.*$', '', name)

    # Удаляем только служебные слова
    words_to_remove = ['купить', 'цена', 'доставка', 'в корзину', '₽', 'руб']
    for word in words_to_remove:
        name = re.sub(f'\\b{word}\\b', '', name, flags=re.IGNORECASE)

    # Удаляем лишние символы в начале/конце
    name = re.sub(r'^[^a-zA-Zа-яА-Я0-9/]+|[^a-zA-Zа-яА-Я0-9/]+$', '', name)

    return name.strip()

class WildberriesSeleniumScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless

    def collect_product_data(self, article: str) -> Optional[ProductData]:
        """Сбор данных о товаре по артикулу"""
        url = f"https://www.wildberries.ru/catalog/{article}/detail.aspx"
        logger.info(f"🔍 Обрабатываем артикул WB: {article}")
        logger.info(f"🌐 Открываем страницу: {url}")
        
        driver = None

        try:
            driver = setup_driver(headless=self.headless)
            driver.set_page_load_timeout(30)
            
            logger.info("🚀 Загружаем страницу...")
            driver.get(url)

            # Ждем загрузки страницы
            wait_for_page_load(driver)
            human_like_delay(3, 5)

            # Закрываем попапы
            close_wildberries_popups(driver)

            # Проверка на блокировку
            if self.is_blocked(driver):
                logger.warning(f"🛡️ Страница заблокирована для артикула {article}")
                return None

            # === Извлечение названия ===
            name = self.extract_product_name(driver, article)
            if not name:
                logger.warning(f"❌ Не удалось извлечь название для артикула {article}")
                return None

            # === Извлечение цены ===
            price = self.extract_product_price(driver, article)
            if not price:
                logger.warning(f"❌ Не удалось извлечь цену для артикула {article}")
                return None

            # === Извлечение старой цены ===
            old_price = self.extract_old_price(driver)

            # === Определение наличия ===
            availability = self.extract_availability(driver, price)

            # === Извлечение рейтинга ===
            rating = self.extract_rating(driver)

            # === Извлечение количества отзывов ===
            reviews_count = self.extract_reviews_count(driver)

            logger.info(f"✅ Успешно собраны данные: {name[:50]}... - {price} руб.")
            
            return ProductData(
                marketplace="Wildberries",
                article=article,
                name=name,
                price=price,
                old_price=old_price,
                availability=availability,
                rating=rating,
                reviews_count=reviews_count,
                url=url,
                collected_at=datetime.now().isoformat()
            )

        except Exception as e:
            logger.error(f"❌ Ошибка при обработке артикула {article}: {str(e)}")
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                    logger.debug("🔚 Драйвер закрыт")
                except Exception as e:
                    logger.debug(f"⚠️ Ошибка при закрытии драйвера: {e}")

    def is_blocked(self, driver) -> bool:
        """Проверка на блокировку или капчу"""
        try:
            page_title = driver.title.lower()
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            
            block_indicators = [
                "включите javascript", "вы не робот", "checking your browser", 
                "please wait", "доступ ограничен", "captcha", "капча",
                "доступ к сайту закрыт", "blocked", "security check"
            ]
            
            for indicator in block_indicators:
                if indicator in body_text or indicator in page_title:
                    logger.warning(f"Обнаружен индикатор блокировки: {indicator}")
                    return True
                    
            return False
        except:
            return False

    def extract_product_name(self, driver, article: str) -> Optional[str]:
        """Извлечение названия товара"""
        name_selectors = [
            "h1.product-page__title",
            "h1[data-link*='goods_name']",
            ".product-page__header h1",
            "h1.product-card__name",
            ".product-page__title-wrap h1",
            "h1.product__name",
            "#productNmId",
            ".product-page__info h1",
            "h1[itemprop='name']",
            ".product-title",
            ".goods-name",
            "h1"
        ]
        
        for selector in name_selectors:
            try:
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                name = element.text.strip()
                if name and len(name) > 3:
                    clean_name = clean_product_name(name)
                    logger.debug(f"📝 Название найдено: {clean_name[:50]}...")
                    return clean_name
            except:
                continue
        
        # Альтернативные методы
        try:
            # Мета-тег title
            meta_title = driver.execute_script("return document.title;")
            if meta_title and len(meta_title) > 10:
                clean_title = re.sub(r'\s*[–-]\s*Wildberries.*$', '', meta_title)
                if len(clean_title) > 10:
                    logger.debug(f"📝 Название из заголовка: {clean_title[:50]}...")
                    return clean_product_name(clean_title)
        except:
            pass

        logger.warning(f"❌ Не удалось найти название товара для артикула {article}")
        return None

    def extract_product_price(self, driver, article: str) -> Optional[float]:
        """Извлечение актуальной цены товара"""
        price = None
        
        # Основные селекторы цены
        price_selectors = [
            "ins.price-block__final-price",
            ".price-block__final-price",
            ".final-price",
            ".lower-price",
            ".j-final-price",
            "[class*='price__lower']",
            ".price-block__price",
            ".price-block__final-price-wrapper",
            ".product-card__price"
        ]
        
        for selector in price_selectors:
            try:
                price_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for price_element in price_elements:
                    price_text = price_element.text.strip()
                    price = extract_price_from_text(price_text)
                    if price:
                        logger.debug(f"💰 Цена из селектора: {price}")
                        return price
            except:
                continue

        # Поиск по символу рубля
        try:
            elements_with_rub = driver.find_elements(By.XPATH, "//*[contains(text(), '₽')]")
            for elem in elements_with_rub:
                parent_text = elem.text
                if not parent_text:
                    parent_text = elem.find_element(By.XPATH, "..").text
                
                price = extract_price_from_text(parent_text)
                if price:
                    logger.debug(f"💰 Цена из элемента с ₽: {price}")
                    return price
        except:
            pass

        # Поиск в JSON данных
        price = self.extract_price_from_scripts(driver, article)
        if price:
            return price

        logger.warning(f"❌ Не удалось извлечь цену для артикула {article}")
        return None

    def extract_price_from_scripts(self, driver, article: str) -> Optional[float]:
        """Извлечение цены из JavaScript данных"""
        try:
            scripts = driver.find_elements(By.TAG_NAME, "script")
            for script in scripts:
                script_content = script.get_attribute("innerHTML") or ""
                
                # Ищем данные конкретного товара
                if f'"{article}"' in script_content or f"'{article}'" in script_content or f'nm:{article}' in script_content:
                    
                    # Паттерны для поиска цен
                    patterns = [
                        r'"price":\s*["]?(\d+[.]?\d*)["]?',
                        r'"finalPrice":\s*["]?(\d+[.]?\d*)["]?',
                        r'"salePriceU":\s*(\d+)',
                        r'"priceU":\s*(\d+)',
                        r'"currentPrice":\s*["]?(\d+[.]?\d*)["]?'
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, script_content)
                        for match in matches:
                            try:
                                price_val = float(match)
                                # Если цена в копейках
                                if 'PriceU' in pattern:
                                    price_val = price_val / 100
                                
                                if 10 <= price_val <= 1000000:
                                    logger.debug(f"💰 Цена из JSON: {price_val}")
                                    return price_val
                            except (ValueError, TypeError):
                                continue
        except Exception as e:
            logger.debug(f"Ошибка при поиске цены в скриптах: {e}")
        
        return None

    def extract_old_price(self, driver) -> Optional[float]:
        """Извлечение старой цены"""
        old_price_selectors = [
            "del.price-block__old-price",
            ".price-block__old-price",
            ".old-price",
            "s.price-block__old-price",
            ".price-block__old-price-wrap",
            "[class*='old-price']"
        ]
        
        for selector in old_price_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    old_price_text = elem.text.strip()
                    old_price = extract_price_from_text(old_price_text)
                    if old_price:
                        logger.debug(f"📉 Старая цена: {old_price}")
                        return old_price
            except:
                continue
        
        return None

    def extract_availability(self, driver, price: float) -> str:
        """Определение наличия товара"""
        # Селекторы указывающие на отсутствие товара
        out_of_stock_selectors = [
            ".product-page__not-available",
            ".out-of-stock",
            ".not-available",
            ".unavailable",
            "[class*='outOfStock']",
            "[class*='notAvailable']",
            ".sold-out",
            ".item-unavailable"
        ]
        
        for selector in out_of_stock_selectors:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed():
                    logger.debug("📦 Товар отсутствует в наличии")
                    return "Нет в наличии"
            except:
                continue
        
        # Селекторы указывающие на наличие
        in_stock_selectors = [
            ".product-page__order-btn",
            ".order-btn",
            "[class*='add-to-cart']",
            ".j-add-to-basket",
            ".buy-btn"
        ]
        
        for selector in in_stock_selectors:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed() and element.is_enabled():
                    logger.debug("📦 Товар в наличии")
                    return "В наличии"
            except:
                continue

        # Если цена 0, вероятно товара нет
        if price == 0:
            return "Неизвестно"
        
        return "В наличии"

    def extract_rating(self, driver) -> Optional[float]:
        """Извлечение рейтинга товара"""
        rating_selectors = [
            ".product-page__rating .rating",
            ".product-rating",
            "[class*='rating']",
            ".rating-stars",
            ".stars",
            "[itemprop='ratingValue']",
            ".product-rating__value"
        ]
        
        for selector in rating_selectors:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                
                # Пробуем разные источники рейтинга
                sources = [
                    element.text.strip(),
                    element.get_attribute("data-rate"),
                    element.get_attribute("data-rating"),
                    element.get_attribute("content"),
                    element.get_attribute("value")
                ]
                
                for source in sources:
                    if source:
                        match = re.search(r'(\d+[.,]\d+)', str(source))
                        if match:
                            rating = float(match.group(1).replace(',', '.'))
                            if 0 <= rating <= 5:
                                logger.debug(f"⭐ Рейтинг: {rating}")
                                return rating
            except:
                continue
        
        return None

    def extract_reviews_count(self, driver) -> int:
        """Извлечение количества отзывов"""
        reviews_selectors = [
            ".product-page__comments-count",
            ".comments-count",
            ".review-count",
            "[class*='review-count']",
            "[class*='comments-count']",
            "[class*='feedbacks-count']",
            ".product-rating__count",
            "[data-link*='feedbacks']"
        ]
        
        for selector in reviews_selectors:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                text = element.text.strip()
                
                # Ищем число в тексте
                match = re.search(r'(\d+)', text.replace(' ', ''))
                if match:
                    count = int(match.group(1))
                    logger.debug(f"💬 Количество отзывов: {count}")
                    return count
            except:
                continue
        
        return 0

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
            # Если это объект ProductData, преобразуем в dict
            if hasattr(item, '__dict__'):
                item = item.__dict__
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

# Функция для массового сбора данных
def collect_multiple_products(articles: list, headless: bool = True) -> list:
    """Сбор данных по нескольким артикулам"""
    scraper = WildberriesSeleniumScraper(headless=headless)
    results = []
    
    for i, article in enumerate(articles):
        logger.info(f"📦 Обрабатываем товар {i+1}/{len(articles)}")
        product_data = scraper.collect_product_data(article)
        if product_data:
            results.append(product_data)
        
        # Задержка между запросами (кроме последнего)
        if i < len(articles) - 1:
            delay = random.uniform(5, 10)
            logger.info(f"⏳ Ждем {delay:.1f} секунд перед следующим запросом...")
            time.sleep(delay)
    
    return results

if __name__ == "__main__":
    # Пример использования
    test_articles = ["358384386", "152113569"]
    
    logger.info("🚀 Тестирование Wildberries парсера")
    
    products = collect_multiple_products(test_articles, headless=False)
    
    if products:
        save_to_json([p.__dict__ for p in products])
        logger.info(f"✅ Успешно собрано {len(products)} товаров")
        for product in products:
            old_price_info = f" (было {product.old_price})" if product.old_price else ""
            rating_info = f", рейтинг: {product.rating}" if product.rating else ""
            reviews_info = f", отзывов: {product.reviews_count}" if product.reviews_count else ""
            
            print(f"📦 {product.article}: {product.name[:50]}...")
            print(f"   💰 {product.price} руб.{old_price_info}{rating_info}{reviews_info}")
            print(f"   📍 {product.availability}")
            print()
    else:
        logger.error("❌ Не удалось собрать данные о товарах")
