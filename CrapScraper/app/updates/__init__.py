from app.updates.service import UpdateService
from app.updates.ultrapack_source_recovery import install_ultrapack_source_recovery

install_ultrapack_source_recovery()

from app.updates.ultrapack_fast_probe import install_ultrapack_fast_probe
from app.updates.fast_transaction import install_fast_transaction
from app.updates.performance_runtime import install_update_performance_runtime

install_ultrapack_fast_probe()
install_fast_transaction()
install_update_performance_runtime()

__all__ = ["UpdateService"]
