"""Реестр ORM-моделей всех модулей для Alembic.

Единственное место, которому разрешено импортировать models чужих модулей:
Alembic должен видеть полную метаданную, чтобы генерировать миграции.
"""

from app.core.db import Base
from app.modules.catalog import models as catalog_models
from app.modules.identity import models as identity_models

__all__ = ["Base", "catalog_models", "identity_models"]
