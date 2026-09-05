from __future__ import annotations

from typing import Any


class _AdditionSourceProxy:
    """Adapta a fonte aprovada ao fluxo de adição sem duplicar autenticação.

    As fontes PluginTheme/UltraPack possuem ``validate_access(job)`` com a lógica
    real de sessão, renovação e descoberta do produto. O executor de adições
    legado chamava apenas ``validate_authentication()`` antes de ``confirm_version``;
    isso falhava quando a sessão persistente ainda não tinha sido carregada.
    """

    def __init__(self, source: Any, job: dict[str, Any]) -> None:
        self._source = source
        self._job = dict(job)
        self._validated_version = ""

    def __getattr__(self, name: str) -> Any:
        return getattr(self._source, name)

    @property
    def kind(self) -> str:
        return str(getattr(self._source, "kind", ""))

    @property
    def display_name(self) -> str:
        return str(getattr(self._source, "display_name", self.kind))

    def validate_authentication(self) -> None:
        validate_access = getattr(self._source, "validate_access", None)
        if callable(validate_access):
            evidence = validate_access(self._job)
            if isinstance(evidence, dict):
                self._validated_version = str(evidence.get("version") or "").strip()
            return
        self._source.validate_authentication()

    def confirm_version(self, job: dict[str, Any]) -> str:
        if self._validated_version:
            return self._validated_version
        return str(self._source.confirm_version(job))

    def download(self, job: dict[str, Any], target: Any) -> Any:
        return self._source.download(job, target)


def install_addition_source_preflight() -> None:
    from app.additions.source import AdditionSourceService

    if getattr(AdditionSourceService, "_crapscraper_source_preflight_installed", False):
        return

    original_source = AdditionSourceService.source

    def source(self: Any, job: dict[str, Any]) -> _AdditionSourceProxy:
        resolved = original_source(self, job)
        if isinstance(resolved, _AdditionSourceProxy):
            return resolved
        return _AdditionSourceProxy(resolved, job)

    AdditionSourceService.source = source
    AdditionSourceService._crapscraper_source_preflight_installed = True


__all__ = ["install_addition_source_preflight", "_AdditionSourceProxy"]
