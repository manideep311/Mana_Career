# Importing every model module here keeps Base.metadata complete for Alembic.
from app.models import audit as audit
from app.models.base import Base

__all__ = ["Base"]
