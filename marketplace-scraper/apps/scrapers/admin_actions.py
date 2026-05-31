"""
Фоновый запуск парсеров из Django Admin.
Делегирует работу с БД management-командам (run_ozon / run_wb),
чтобы избежать конфликтов сигнатур моделей.
"""
import logging
import threading
from django.core.management import call_command
from django.contrib import messages
from django.utils import timezone

logger = logging.getLogger(__name__)


def run_scraper_async(marketplace: str, request=None):
    """
    Запускает парсер в отдельном потоке.
    marketplace: 'wb' или 'ozon'
    """
    command_name = f'run_{marketplace}'
    mp_display = 'Ozon' if marketplace == 'ozon' else 'Wildberries'

    def _run():
        try:
            logger.info(f"🚀 Admin (thread): запуск {mp_display}")
            
            # Management-команда сама создаст ScrapeRun, обновит статус и закроет сессию
            call_command(command_name, force=True, verbosity=0)
            
            logger.info(f"✅ Admin (thread): {mp_display} завершён успешно")
            
        except Exception as e:
            logger.error(f" Admin (thread): ошибка {mp_display}: {e}", exc_info=True)
    
    # Запускаем в фоне (daemon=True гарантирует завершение при остановке Gunicorn)
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
