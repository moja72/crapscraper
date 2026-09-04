from __future__ import annotations

"""Compatibilidade para atalhos antigos.

A aplicação canônica vive em ``../main.py``. Este arquivo existe apenas para que
atalhos/comandos antigos não iniciem acidentalmente a árvore ``CrapScraper/app``
legada.
"""

from pathlib import Path
import runpy


if __name__ == "__main__":
    root_main = Path(__file__).resolve().parents[1] / "main.py"
    runpy.run_path(str(root_main), run_name="__main__")
