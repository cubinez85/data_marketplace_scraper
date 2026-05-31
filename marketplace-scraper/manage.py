#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def main():
    """Run administrative tasks."""
    # Загружаем .env ДО импорта Django, чтобы настройки (DB, SECRET_KEY и т.д.)
    # были доступны при инициализации config.settings
    base_dir = Path(__file__).resolve().parent
    env_path = base_dir / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
