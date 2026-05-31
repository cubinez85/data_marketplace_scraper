"""
Простые представления для статус-страниц и health checks.
"""
from django.http import JsonResponse, HttpResponse
from django.db import connections
from django.conf import settings
import datetime

def status_page(request):
    """
    HTML-страница статуса на корне сайта (/).
    Показывает время, статус БД и ссылки на доступные эндпоинты.
    """
    # Проверка подключения к БД
    db_status = "❌ Offline"
    try:
        connections['default'].cursor()
        db_status = "✅ Online"
    except Exception:
        pass

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Marketplace Scraper — Статус</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
                   background: #f8f9fa; color: #333; margin: 0; padding: 40px; display: flex; 
                   justify-content: center; align-items: center; min-height: 100vh; }}
            .card {{ background: white; padding: 30px; border-radius: 12px; 
                    box-shadow: 0 4px 20px rgba(0,0,0,0.08); max-width: 500px; width: 100%; }}
            h1 {{ margin: 0 0 20px; font-size: 24px; color: #2c3e50; }}
            .status-item {{ display: flex; justify-content: space-between; padding: 12px 0; 
                           border-bottom: 1px solid #eee; }}
            .status-item:last-child {{ border-bottom: none; }}
            .label {{ color: #666; }}
            .value {{ font-weight: 600; }}
            .ok {{ color: #27ae60; }}
            .err {{ color: #e74c3c; }}
            .links {{ margin-top: 25px; padding-top: 20px; border-top: 2px dashed #eee; }}
            .links a {{ display: block; margin: 8px 0; text-decoration: none; color: #3498db; }}
            .links a:hover {{ text-decoration: underline; }}
            footer {{ margin-top: 30px; text-align: center; color: #999; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>📦 Marketplace Scraper</h1>
            
            <div class="status-item">
                <span class="label">Статус сервиса</span>
                <span class="value ok">🟢 Работает</span>
            </div>
            <div class="status-item">
                <span class="label">База данных</span>
                <span class="value {'ok' if 'Online' in db_status else 'err'}">{db_status}</span>
            </div>
            <div class="status-item">
                <span class="label">Время сервера</span>
                <span class="value">{now}</span>
            </div>
            <div class="status-item">
                <span class="label">Режим</span>
                <span class="value">{'🧪 Debug' if settings.DEBUG else '🚀 Production'}</span>
            </div>

            <div class="links">
                <strong>🔗 Доступные разделы:</strong>
                <a href="/admin/">🔐 Django Admin</a>
                <a href="/api/v1/products/">📦 API: Товары</a>
                <a href="/api/v1/products/stats/">📊 API: Статистика</a>
                <a href="/api/v1/targets/">🎯 API: Цели парсинга</a>
                <a href="/api/v1/scrape-runs/">📋 API: История запусков</a>
            </div>
            
            <footer>
                Marketplace Scraper v1.0<br>
                Django + DRF + PostgreSQL
            </footer>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)


def health_check(request):
    """
    JSON endpoint для мониторинга (Kubernetes, systemd, UptimeRobot).
    Возвращает 200, если БД доступна.
    """
    try:
        connections['default'].cursor()
        return JsonResponse({'status': 'ok', 'database': 'connected'}, status=200)
    except Exception as e:
        return JsonResponse({'status': 'error', 'database': 'disconnected', 'error': str(e)}, status=503)
