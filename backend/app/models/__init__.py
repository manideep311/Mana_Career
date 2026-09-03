# Importing every model module here keeps Base.metadata complete for Alembic.
from app.models import audit as audit
from app.models import auth as auth
from app.models import eval as eval
from app.models import job as job
from app.models import match as match
from app.models import profile as profile
from app.models import resume as resume
from app.models import skill as skill
from app.models import user as user
from app.models.base import Base

__all__ = ["Base"]
