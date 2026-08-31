# Importing every model module here keeps Base.metadata complete for Alembic.
from app.models import audit as audit
from app.models import auth as auth
from app.models import user as user
from app.models.base import Base

__all__ = ["Base"]
