from __future__ import annotations

"""Compatibilidade para atalhos antigos.

A aplicação canônica vive em ``../main.py``. Este arquivo existe apenas para que
atalhos/comandos antigos não iniciem acidentalmente a árvore ``CrapScraper/app``
legada.
"""

import os
from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    root_main = root / "main.py"
    # O diretório desta cópia legada também possui um pacote chamado app. A raiz
    # precisa vir primeiro no sys.path para que imports ``app.*`` usem a aplicação
    # atual e não a árvore antiga.
    root_text = str(root)
    sys.path[:] = [item for item in sys.path if str(Path(item or ".").resolve()) != str(Path(__file__).resolve().parent)]
    sys.path.insert(0, root_text)
    os.chdir(root)
    runpy.run_path(str(root_main), run_name="__main__")
