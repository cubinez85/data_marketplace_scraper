from django.contrib import admin
from django.urls import path, include
from apps.api.views_status import status_page, health_check  # ← Импорт

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API маршруты (должны идти до пустого пути, если роутер не использует префикс)
    # Но так как у нас есть префикс 'api/v1/' внутри include, порядок не критичен
    path('', include('apps.api.urls')), 
    
    # Корневой статус и health-check
    path('', status_page, name='home'),              # ← Главная страница (ваш запрос)
    path('health/', health_check, name='health'),    # ← Для мониторинга
]
