Система для сбора данных о товарах конкурентов с крупных маркетплейсов (Wildberries, Ozon, Яндекс.Маркет и др.)
с целью мониторинга цен, наличия товаров и рейтингов для конкурентного анализа.
Функциональные требования
Основные задачи:
Получение данных о товарах конкурентов:
Цена товара (текущая, старая, со скидкой)
Наличие товара (в наличии, под заказ, нет в наличии)
Рейтинг товара и количество отзывов
Основные характеристики товара (название, бренд, категория, артикул)
Сохранение данных:
Автоматическое сохранение в структурированном формате (CSV)
Интеграция с Google Sheets для автоматического обновления таблиц
Поддержка истории изменений цен и наличия
Группировка данных по дате сбора, маркетплейсу, категории товаров
Технические требования
Методы сбора данных:
Приоритетный метод — API-интеграции:
Использование неофициальных API маркетплейсов
Интеграция с сервисами-агрегаторами:
WB Stat (для Wildberries)
MPStats (агрегатор данных маркетплейсов)
Другие доступные сервисы
Обработка ответов API и извлечение нужных данных
Резервный метод — веб-парсинг:
При недоступности API использовать парсинг веб-страниц
Обязательные меры безопасности и этичности:
Использование прокси-серверов с ротацией
Ротация User-Agent для имитации разных браузеров
Ограничение частоты запросов (rate limiting) для избежания блокировок
Соблюдение robots.txt и этических норм парсинга
Задержки между запросами для снижения нагрузки на серверы
Технические детали:
Обработка ошибок и повторные попытки при сбоях
Логирование процесса сбора данных
Валидация собранных данных перед сохранением
Поддержка параллельного сбора данных с нескольких маркетплейсов
Конфигурируемые параметры (список товаров/категорий для мониторинга, частота обновления)
Формат вывода данных
CSV файлы:
Структурированные таблицы с колонками: Дата, Маркетплейс, Артикул, Название, Цена, Старая цена, Наличие, Рейтинг,
Количество отзывов, Ссылка
Разделение файлов по датам или маркетплейсам (опционально)
Google Sheets:
Автоматическое обновление таблиц через Google Sheets API
Поддержка нескольких листов (по маркетплейсам или категориям)
Форматирование данных для удобного анализа
Возможность настройки автоматического обновления по расписанию
Дополнительные требования
Конфигурационный файл для настройки параметров (API ключи, прокси, списки товаров)
Документация по использованию системы
Поддержка командной строки или веб-интерфейса для управления сбором данных
Возможность фильтрации и анализа собранных данных

# Обновление системы
sudo apt update
sudo apt upgrade -y

# Установка Python и pip
sudo apt install python3 python3-pip python3-venv -y

# Установка Chrome браузера
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg

# Добавляем репозиторий
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# Обновляем и устанавливаем
sudo apt update
sudo apt install google-chrome-stable -y

# Проверяем версию Chrome
google-chrome --version

requirements.txt:

selenium==4.15.0
selenium-stealth==1.0.6
undetected-chromedriver==3.5.0
webdriver-manager==4.0.1
pandas==2.1.0
openpyxl==3.1.2
PyYAML==6.0.1
requests==2.31.0
python-dateutil==2.8.2
beautifulsoup4==4.12.2
lxml==4.9.3

тестовый скрипт test_installation.py:

# test_installation.py
import sys

def check_imports():
    modules = [
        'selenium', 'selenium_stealth', 'undetected_chromedriver',
        'webdriver_manager', 'pandas', 'yaml', 'requests', 'json',
        'datetime', 'os', 're', 'logging', 'time', 'random'
    ]
    
    print("🔍 Проверка импортов...")
    for module in modules:
        try:
            __import__(module)
            print(f"✅ {module} - OK")
        except ImportError as e:
            print(f"❌ {module} - Ошибка: {e}")

def check_chrome():
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        driver = webdriver.Chrome(options=options)
        driver.quit()
        print("✅ Chrome драйвер - OK")
    except Exception as e:
        print(f"❌ Chrome драйвер - Ошибка: {e}")

if __name__ == "__main__":
    print("Python version:", sys.version)
    print("\n" + "="*50)
    check_imports()
    print("\n" + "="*50)
    check_chrome()

python test_installation.py

#Команды запуска из терминала
python manage.py run_ozon --force --limit 1
python manage.py run_wb --force --limit 1

# или через systemd службы для каждого маркета своя служба
# http://market-scraper.cubinez.ru/
