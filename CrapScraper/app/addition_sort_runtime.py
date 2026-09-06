"""Compatibility entry point: listing is owned by the repository and service."""
from app.additions.service import AdditionService

_list = AdditionService.list

def install_addition_sort_runtime() -> None:
    # Do not overwrite auto-materialization or source filtering installed earlier.
    return
