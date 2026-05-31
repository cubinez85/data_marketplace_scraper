"""
Wildberries Selenium Scraper — Django-интеграция.
Работает по прямым ссылкам на карточки товаров (артикулы).
Все данные возвращаются в формате apps.scrapers.storage.ProductData.
Конфигурация передаётся через dict (обычно settings.SCRAPER_CONFIG['wb']).
"""
import time
import random
import re
import logging
from django.utils import timezone
from typing import Optional, List, Dict, Any, Callable

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service


from apps.scrapers.storage import ProductData

logger = logging.getLogger(__name__)


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def setup_driver(headless: bool = True, proxy: Optional[str] = None) -> webdriver.Chrome:
    """Настройка Chrome-драйвера с анти-детект параметрами."""
    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-features=VizDisplayCompositor')

    if headless:
        options.add_argument('--headless=new')

    options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    options.add_argument('--accept-lang=ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    if proxy:
        options.add_argument(f'--proxy-server={proxy}')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    stealth(
        driver,
        languages=["ru-RU", "ru"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )

    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: function() {return undefined;}})"
    )
    return driver


def human_like_delay(min_sec: float = 1.0, max_sec: float = 3.0) -> None:
    """Случайная задержка для имитации поведения человека."""
    time.sleep(random.uniform(min_sec, max_sec))


def wait_for_page_load(driver: webdriver.Chrome, timeout: int = 15) -> None:
    """Ожидание полной загрузки DOM."""
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script('return document.readyState') == 'complete'
    )


def close_wildberries_popups(driver: webdriver.Chrome) -> None:
    """Закрытие типовых попапов WB (куки, геолокация, модалки)."""
    try:
        time.sleep(1.5)
        for selector in [
            '.cookie-notification__button', '.cookies__button', '[data-wba-header-name*="Cookie"]',
            '.geo__close', '.location__close', '[data-wba-header-name*="Location"]',
            'button[aria-label*="Закрыть"]', '.popup__close', '.j-close', '.modal__close'
        ]:
            try:
                btns = driver.find_elements(By.CSS_SELECTOR, selector)
                for btn in btns:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(0.4)
                        break
            except:
                continue
    except Exception as e:
        logger.debug(f"⚠️ WB: ошибка закрытия попапов: {e}")


def extract_price_from_text(text: Optional[str]) -> Optional[float]:
    """Безопасное извлечение цены из строки."""
    if not text:
        return None
    try:
        clean = re.sub(r'[^\d\s,.]', '', text.strip()).replace(' ', '').replace(',', '.')
        if clean:
            price = float(clean)
            return price if 1 <= price <= 10_000_000 else None
    except (ValueError, TypeError):
        pass
    return None


def clean_product_name(name: Optional[str]) -> str:
    """Очистка названия от мусора и служебных слов."""
    if not name:
        return "Неизвестный товар"
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'\s*[\d\s,.]+[₽₽\.]*\s*$', '', name)
    for word in ['купить', 'цена', 'доставка', 'в корзину', 'руб', '₽']:
        name = re.sub(rf'\b{word}\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^[^a-zA-Zа-яА-Я0-9/\-\(\)]+|[^a-zA-Zа-яА-Я0-9/\-\(\)]+$', '', name)
    return name.strip() or "Неизвестный товар"


# =============================================================================
# ОСНОВНОЙ КЛАСС ПАРСЕРА
# =============================================================================

class WildberriesSeleniumScraper:
    """
    Парсер Wildberries.
    
    Использование:
        config = settings.SCRAPER_CONFIG.get('wb', {})
        scraper = WildberriesSeleniumScraper(config=config)
        product = scraper.collect_product_data("12345678")
        products = scraper.collect_multiple(["111", "222"], on_progress=callback)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.headless: bool = self.config.get('headless', True)
        self.proxy: Optional[str] = self.config.get('proxy')
        self.timeout: int = self.config.get('timeout', 30)
        self.delay_range: tuple = tuple(self.config.get('delay_range', (1, 3)))
        self.request_delay: tuple = tuple(self.config.get('request_delay', (3, 7)))

    def collect_product_data(self, article: str) -> Optional[ProductData]:
        """
        Сбор данных по одному артикулу.
        Returns: ProductData или None при ошибке/блокировке.
        """
        url = f"https://www.wildberries.ru/catalog/{article}/detail.aspx"
        logger.info(f"🔍 WB: {article} → {url}")

        driver = None
        try:
            driver = setup_driver(headless=self.headless, proxy=self.proxy)
            driver.set_page_load_timeout(self.timeout)
            driver.get(url)
            wait_for_page_load(driver)
            human_like_delay(*self.delay_range)
            close_wildberries_popups(driver)

            if self._is_blocked(driver):
                logger.warning(f"🛡️ WB: блокировка/капча для {article}")
                return None

            name = self._extract_name(driver, article)
            if not name:
                return None

            price = self._extract_price(driver, article)
            if not price:
                return None

            old_price = self._extract_old_price(driver)
            availability_str = self._extract_availability(driver, price)
            rating = self._extract_rating(driver)
            reviews_count = self._extract_reviews_count(driver)

            logger.info(f"✅ WB: {article} | {name[:40]}... | {price}₽")

            return ProductData(
                marketplace='wb',
                article=article,
                name=name,
                price=price,
                old_price=old_price,
                availability=(availability_str == "В наличии"),  # bool для ORM
                rating=rating,
                reviews_count=reviews_count,
                url=url,
                collected_at=timezone.now(),
                image_url=self._extract_image_url(driver),
                category=self._extract_category(driver),
                extra_data={'raw_title': name}
            )

        except Exception as e:
            logger.error(f"❌ WB: ошибка парсинга {article}: {e}", exc_info=True)
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.debug(f"⚠️ WB: ошибка закрытия драйвера: {e}")

    def collect_multiple(
        self,
        articles: List[str],
        on_progress: Optional[Callable[[int, int, int], None]] = None
    ) -> List[ProductData]:
        """
        Массовый сбор данных.
        on_progress(current: int, total: int, success: int)
        """
        results: List[ProductData] = []
        total = len(articles)

        for i, article in enumerate(articles):
            product = self.collect_product_data(article)
            if product:
                results.append(product)

            if on_progress:
                on_progress(i + 1, total, len(results))

            if i < total - 1:
                delay = random.uniform(*self.request_delay)
                logger.debug(f"⏳ WB: пауза {delay:.1f}с перед следующим запросом")
                time.sleep(delay)

        logger.info(f"📊 WB: собрано {len(results)}/{total} товаров")
        return results

    # =========================================================================
    # ВНУТРЕННИЕ МЕТОДЫ ИЗВЛЕЧЕНИЯ (приватные)
    # =========================================================================

    def _is_blocked(self, driver: webdriver.Chrome) -> bool:
        try:
            text = (driver.title + ' ' + driver.find_element(By.TAG_NAME, "body").text).lower()
            blockers = [
                "включите javascript", "вы не робот", "checking your browser",
                "please wait", "доступ ограничен", "captcha", "капча",
                "security check", "access denied", "403"
            ]
            return any(b in text for b in blockers)
        except:
            return False

    def _extract_name(self, driver: webdriver.Chrome, article: str) -> Optional[str]:
        selectors = [
            "h1.product-page__title", "h1[data-link*='goods_name']",
            ".product-page__header h1", "h1.product-card__name",
            ".product-page__title-wrap h1", "h1[itemprop='name']",
            ".product-title", ".goods-name", "h1"
        ]
        for sel in selectors:
            try:
                el = WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                name = el.text.strip()
                if name and len(name) > 3:
                    return clean_product_name(name)
            except:
                continue

        # Fallback: document.title
        try:
            title = driver.execute_script("return document.title;")
            if title:
                clean = re.sub(r'\s*[–-]\s*Wildberries.*$', '', title).strip()
                if len(clean) > 10:
                    return clean_product_name(clean)
        except:
            pass

        logger.warning(f"❌ WB: не найдено название для {article}")
        return None

    def _extract_price(self, driver: webdriver.Chrome, article: str) -> Optional[float]:
        for sel in [
            "ins.price-block__final-price", ".price-block__final-price",
            ".final-price", ".lower-price", ".j-final-price",
            "[class*='price__lower']", ".price-block__price"
        ]:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    price = extract_price_from_text(el.text)
                    if price:
                        return price
            except:
                continue

        # Поиск по символу ₽
        try:
            for el in driver.find_elements(By.XPATH, "//*[contains(text(), '₽')]"):
                text = el.text or el.find_element(By.XPATH, "..").text
                price = extract_price_from_text(text)
                if price:
                    return price
        except:
            pass

        price = self._extract_price_from_scripts(driver, article)
        if price:
            return price

        logger.warning(f"❌ WB: не найдена цена для {article}")
        return None

    def _extract_price_from_scripts(self, driver: webdriver.Chrome, article: str) -> Optional[float]:
        try:
            for script in driver.find_elements(By.TAG_NAME, "script"):
                content = script.get_attribute("innerHTML") or ""
                if f'"{article}"' in content or f"'{article}'" in content:
                    for pattern in [
                        r'"price":\s*"?(\d+[.]?\d*)"?',
                        r'"finalPrice":\s*"?(\d+[.]?\d*)"?',
                        r'"salePriceU":\s*(\d+)',
                        r'"priceU":\s*(\d+)',
                    ]:
                        for match in re.findall(pattern, content):
                            try:
                                val = float(match)
                                if 'PriceU' in pattern:
                                    val /= 100  # копейки → рубли
                                if 1 <= val <= 10_000_000:
                                    return val
                            except:
                                continue
        except Exception as e:
            logger.debug(f"⚠️ WB: ошибка парсинга скриптов: {e}")
        return None

    def _extract_old_price(self, driver: webdriver.Chrome) -> Optional[float]:
        for sel in [
            "del.price-block__old-price", ".price-block__old-price",
            ".old-price", "s.price-block__old-price", "[class*='old-price']"
        ]:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    price = extract_price_from_text(el.text)
                    if price:
                        return price
            except:
                continue
        return None

    def _extract_availability(self, driver: webdriver.Chrome, price: float) -> str:
        for sel in [
            ".product-page__not-available", ".out-of-stock",
            ".not-available", ".unavailable", "[class*='outOfStock']"
        ]:
            try:
                if driver.find_element(By.CSS_SELECTOR, sel).is_displayed():
                    return "Нет в наличии"
            except:
                continue

        for sel in [
            ".product-page__order-btn", ".order-btn",
            "[class*='add-to-cart']", ".j-add-to-basket"
        ]:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed() and btn.is_enabled():
                    return "В наличии"
            except:
                continue

        return "В наличии" if price > 0 else "Неизвестно"

    def _extract_rating(self, driver: webdriver.Chrome) -> Optional[float]:
        for sel in [
            ".product-page__rating .rating", ".product-rating",
            "[itemprop='ratingValue']", ".product-rating__value",
            "[class*='rating']", ".stars"
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                for attr in ['text', 'data-rate', 'data-rating', 'content', 'value']:
                    val = getattr(el, attr, lambda: None)() if attr != 'text' else el.text
                    if val:
                        match = re.search(r'(\d+[.,]\d+)', str(val))
                        if match:
                            rating = float(match.group(1).replace(',', '.'))
                            if 0 <= rating <= 5:
                                return rating
            except:
                continue
        return None

    def _extract_reviews_count(self, driver: webdriver.Chrome) -> int:
        for sel in [
            ".product-page__comments-count", ".comments-count",
            ".review-count", "[class*='feedbacks-count']",
            ".product-rating__count", "[data-link*='feedbacks']"
        ]:
            try:
                text = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                match = re.search(r'(\d+)', text.replace(' ', ''))
                if match:
                    return int(match.group(1))
            except:
                continue
        return 0

    def _extract_image_url(self, driver: webdriver.Chrome) -> Optional[str]:
        selectors = [
            'meta[property="og:image"]',
            'img.product-page__photo-img',
            '.photo-zoom__main img',
            '[data-zoom-image]',
            '.j-product-photo img'
        ]
        for sel in selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                url = el.get_attribute('content') or el.get_attribute('src') or el.get_attribute('data-src')
                if url and url.startswith('http'):
                    return url.split('?')[0]
            except:
                continue
        return None

    def _extract_category(self, driver: webdriver.Chrome) -> Optional[str]:
        try:
            breadcrumbs = driver.find_elements(By.CSS_SELECTOR, '.breadcrumbs__item, [itemprop="itemListElement"]')
            if len(breadcrumbs) >= 2:
                return breadcrumbs[-2].text.strip()
        except:
            pass
        return None
