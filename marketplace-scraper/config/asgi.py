"""
ASGI config for marketplace-scraper project.

Exposes the ASGI callable as a module-level variable named ``application``.
Готово для будущего использования Uvicorn/Daphne или WebSockets.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from django.core.asgi import get_asgi_application

# Аналогично wsgi.py: гарантируем доступ к переменным окружения
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / '.env', override=False)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_asgi_application()
