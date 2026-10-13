"""Выгрузка OpenAPI-схемы в файл — источник для генерации TS-клиента фронтенда.

    uv run python -m scripts.export_openapi ../frontend/openapi.json

В CI схема выгружается заново и сравнивается с закоммиченной: расхождение контракта
бэкенда и фронтенда валит сборку.
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    schema = app.openapi()
    target.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"OpenAPI -> {target} ({len(schema['paths'])} путей)")


if __name__ == "__main__":
    main()
