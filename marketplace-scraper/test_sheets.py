#!/usr/bin/env python
"""
Минимальный тест записи в Google Sheets.
Запуск: python test_sheets.py
"""
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

from dotenv import load_dotenv
load_dotenv()

# Настройки
SPREADSHEET_ID = os.getenv('GOOGLE_SHEETS_SPREADSHEET_ID', '').strip()
CREDENTIALS_PATH = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH', 'credentials.json').strip()
WORKSHEET_NAME = os.getenv('GOOGLE_SHEETS_WORKSHEET', 'Products').strip()

print(f"🔍 Тест подключения к Google Sheets")
print(f"📄 Таблица: {SPREADSHEET_ID}")
print(f"📋 Лист: '{WORKSHEET_NAME}'")
print(f"🔑 Ключи: {CREDENTIALS_PATH}\n")

# Проверка файла ключей
if not os.path.exists(CREDENTIALS_PATH):
    print(f"❌ Файл ключей не найден: {CREDENTIALS_PATH}")
    sys.exit(1)

try:
    import gspread
    from google.oauth2.service_account import Credentials
    
    print("✅ Библиотеки импортированы")
    
    # Авторизация
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/spreadsheets'
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scope)
    client = gspread.authorize(creds)
    print("✅ Авторизация успешна")
    
    # Открытие таблицы
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    print(f"✅ Таблица открыта: {spreadsheet.title}")
    
    # Получение или создание листа
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        print(f"✅ Лист найден: '{WORKSHEET_NAME}'")
    except gspread.exceptions.WorksheetNotFound:
        print(f"⚠️ Лист '{WORKSHEET_NAME}' не найден, создаю...")
        worksheet = spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows=100, cols=10)
        print(f"✅ Лист создан")
    
    # 🔴 ТЕСТОВАЯ ЗАПИСЬ
    test_row = [
        'TEST',                    # Дата сбора
        'GoogleTest',              # Маркетплейс
        '999999999',               # Артикул
        'Тестовая запись',         # Название
        '123.45',                  # Цена
        '',                        # Старая цена
        'Yes',                     # Наличие
        '5.0',                     # Рейтинг
        '1',                       # Отзывов
        'https://test.local'       # Ссылка
    ]
    
    print(f"\n📝 Отправляю тестовую строку: {test_row}")
    
    # Прямая запись без batch_update
    result = worksheet.append_row(test_row, value_input_option='USER_ENTERED')
    
    print(f"✅ API ответ: {result}")
    print(f"🎉 Тест завершён! Проверьте таблицу — последняя строка должна содержать 'Тестовая запись'")
    
    # Покажем список листов для отладки
    print(f"\n📋 Все листы в таблице:")
    for ws in spreadsheet.worksheets():
        print(f"  - '{ws.title}' ({ws.row_count} строк, {ws.col_count} колонок)")
    
except gspread.exceptions.APIError as e:
    print(f"❌ API ошибка: {e}")
    if hasattr(e, 'response'):
        print(f"📄 Тело ответа: {e.response.text}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Ошибка: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
