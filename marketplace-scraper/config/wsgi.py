"""
WSGI config for marketplace-scraper project.

Exposes the WSGI callable as a module-level variable named ``application``.
Gunicorn использует этот файл как точку входа.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from django.core.wsgi import get_wsgi_application

# Загружаем .env ДО импорта Django.
# Это обязательно, так как Gunicorn вызывает этот файл напрямую,
# минуя manage.py и settings.py.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / '.env', override=False)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
