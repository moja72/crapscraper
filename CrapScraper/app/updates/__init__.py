from app.updates.service import UpdateService
from app.updates.ultrapack_source_recovery import install_ultrapack_source_recovery

install_ultrapack_source_recovery()

__all__ = ["UpdateService"]
