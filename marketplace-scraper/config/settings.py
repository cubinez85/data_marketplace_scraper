"""
Django settings for marketplace-scraper project.
Production-ready конфигурация с поддержкой PostgreSQL, DRF, Selenium-парсеров.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Убирает предупреждения W042 о AutoField в моделях
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
# 1. БАЗОВЫЕ НАСТРОЙКИ
# =============================================================================

# Загрузка .env ДО импорта чего-либо
env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=False)

BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# 2. БЕЗОПАСНОСТЬ И ОТЛАДКА
# =============================================================================

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY and os.getenv('DEBUG', 'False').lower() != 'true':
    raise ValueError("❌ SECRET_KEY не установлен в .env. Обязательно для production.")

DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# ALLOWED_HOSTS: парсинг с удалением пустых элементов
_raw_hosts = os.getenv('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(',') if h.strip()]
if DEBUG:
    ALLOWED_HOSTS += ['localhost', '127.0.0.1', '0.0.0.0', '[::1]']

# CSRF_TRUSTED_ORIGINS для HTTPS (если используете прокси с SSL)
CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',')
CSRF_TRUSTED_ORIGINS = [h.strip() for h in CSRF_TRUSTED_ORIGINS if h.strip()]


# =============================================================================
# 3. ПРИЛОЖЕНИЯ
# =============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',

    # Local apps
    'apps.scrapers',
    'apps.api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

# =============================================================================
# 4. ШАБЛОНЫ
# =============================================================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# =============================================================================
# 5. БАЗА ДАННЫХ (PostgreSQL)
# =============================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'marketplace_db'),
        'USER': os.getenv('DB_USER', 'marketplace_user'),
        'PASSWORD': os.getenv('DB_PASS', ''),
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            'connect_timeout': 5,
            'options': '-c statement_timeout=60000',  # 60 сек таймаут на запрос
        },
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '0')),
    }
}

# =============================================================================
# 6. ВАЛИДАЦИЯ ПАРОЛЕЙ
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =============================================================================
# 7. ЛОКАЛИЗАЦИЯ И ВРЕМЯ
# =============================================================================

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

# =============================================================================
# 8. СТАТИКА И МЕДИА
# =============================================================================

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# =============================================================================
# 9. DJANGO REST FRAMEWORK
# =============================================================================

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
}

# =============================================================================
# 10. НАСТРОЙКИ СКРАПЕРОВ (ТОЛЬКО ТЕХНИЧЕСКИЕ ПАРАМЕТРЫ)
# =============================================================================

SCRAPER_CONFIG = {
    'global': {
        'max_retries': int(os.getenv('SCRAPER_MAX_RETRIES', '3')),
        'retry_delay': float(os.getenv('SCRAPER_RETRY_DELAY', '2.0')),
    },
    'wb': {
        'headless': os.getenv('WB_HEADLESS', 'True').lower() == 'true',
        'proxy': os.getenv('WB_PROXY') or None,
        'timeout': int(os.getenv('WB_TIMEOUT', '30')),
        'delay_range': tuple(map(float, os.getenv('WB_DELAY_RANGE', '1,3').split(','))),
        'request_delay': tuple(map(float, os.getenv('WB_REQUEST_DELAY', '3,7').split(','))),
    },
    'ozon': {
        'headless': os.getenv('OZON_HEADLESS', 'True').lower() == 'true',
        'proxy': os.getenv('OZON_PROXY') or None,
        'timeout': int(os.getenv('OZON_TIMEOUT', '30')),
        'max_scrolls': int(os.getenv('OZON_MAX_SCROLLS', '10')),
        'min_price': int(os.getenv('OZON_MIN_PRICE', '100')),
        'max_price': int(os.getenv('OZON_MAX_PRICE', '10000000')),
        'request_delay': tuple(map(float, os.getenv('OZON_REQUEST_DELAY', '5,10').split(','))),
    },
    'storage': {
        'csv_enabled': os.getenv('CSV_ENABLED', 'True').lower() == 'true',
        'csv_path': os.getenv('CSV_PATH', 'data/products_{date}.csv'),
        'google_sheets_enabled': os.getenv('GOOGLE_SHEETS_ENABLED', 'False').lower() == 'true',
        'google_sheets_worksheet': os.getenv('GOOGLE_SHEETS_WORKSHEET', 'Products'),
    }
}

# =============================================================================
# 11. GOOGLE SHEETS API
# =============================================================================

_creds_path = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH', 'credentials.json')
GOOGLE_SHEETS_CREDENTIALS_PATH = Path(_creds_path).resolve() if _creds_path else None
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv('GOOGLE_SHEETS_SPREADSHEET_ID')

# =============================================================================
# 12. ЛОГИРОВАНИЕ
# =============================================================================

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# =============================================================================
# ЛОГИРОВАНИЕ (DEBUG-РЕЖИМ)
# =============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'scraper.log',
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'DEBUG',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',  # 🟢 Фреймворк логирует только важное
            'propagate': False,
        },
        'apps.scrapers': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG', # 🔍 Парсеры пишут всё: запросы, цены, ошибки
            'propagate': False,
        },
        'gunicorn.error': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# =============================================================================
# 13. PRODUCTION SECURITY (раскомментируйте при деплое на реальный домен)
# =============================================================================

# if not DEBUG:
#     SECURE_SSL_REDIRECT = True
#     SESSION_COOKIE_SECURE = True
#     CSRF_COOKIE_SECURE = True
#     SECURE_BROWSER_XSS_FILTER = True
#     SECURE_CONTENT_TYPE_NOSNIFF = True
#     X_FRAME_OPTIONS = 'DENY'
#     SECURE_HSTS_SECONDS = 3600
#     SECURE_HSTS_INCLUDE_SUBDOMAINS = True
#     SECURE_HSTS_PRELOAD = True

# =============================================================================
# 14. ПРОЧИЕ НАСТРОЙКИ
# =============================================================================

DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('DATA_UPLOAD_MAX_MEMORY_SIZE', '2621440'))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('FILE_UPLOAD_MAX_MEMORY_SIZE', '2621440'))

EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
if not DEBUG and EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend':
    EMAIL_HOST = os.getenv('EMAIL_HOST')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
    DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@yourdomain.com')

# Admin contact (для уведомлений, НЕ для аутентификации)
ADMIN_CONTACT_EMAIL = os.getenv('ADMIN_EMAIL', '')
if ADMIN_CONTACT_EMAIL and not DEBUG:
    ADMINS = [('Admin', ADMIN_CONTACT_EMAIL)]
    SERVER_EMAIL = ADMIN_CONTACT_EMAIL

# Celery (опционально)
# if os.getenv('USE_CELERY', 'False').lower() == 'true':
#     CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
#     CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
#     CELERY_ACCEPT_CONTENT = ['json']
#     CELERY_TASK_SERIALIZER = 'json'
#     CELERY_TIMEZONE = TIME_ZONE

# =============================================================================
# 15. СИСТЕМНЫЕ ПРОВЕРКИ (только критические)
# =============================================================================

if not DEBUG:
    # Проверяем только действительно критичные настройки
    if not os.getenv('DB_PASS'):
        raise ValueError("❌ DB_PASS не установлен в .env — обязательно для production!")
    
    # Проверяем, что ALLOWED_HOSTS не пустой в production
    if not ALLOWED_HOSTS:
        raise ValueError("❌ ALLOWED_HOSTS пуст в production — укажите домен/IP в .env")
