"""Clientes externos deliberadamente read-only."""

from app.integrations.wordpress import WriteOperationDisabledError

__all__ = ["WriteOperationDisabledError"]
