"""Реестр ORM-моделей всех модулей для Alembic.

Единственное место, которому разрешено импортировать models чужих модулей:
Alembic должен видеть полную метаданную, чтобы генерировать миграции.
"""

from app.core.db import Base
from app.modules.booking import models as booking_models
from app.modules.catalog import models as catalog_models
from app.modules.identity import models as identity_models
from app.modules.notifications import models as notifications_models
from app.modules.orders import models as orders_models
from app.shared import inbox, outbox

__all__ = [
    "Base",
    "booking_models",
    "catalog_models",
    "identity_models",
    "inbox",
    "notifications_models",
    "orders_models",
    "outbox",
]
