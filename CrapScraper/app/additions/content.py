from __future__ import annotations
import re
from typing import Any

def valid_content(value:dict[str,Any])->bool:return len(str(value.get("short_description") or "").strip())>=180 and len(str(value.get("content") or "").strip())>=300
def normalize_list(value:Any)->list[str]:
    rows=value if isinstance(value,list) else re.split(r"[,;]",str(value or ""));out=[]
    for item in rows:
        text=" ".join(str(item).split())
        if text and text.casefold() not in {x.casefold() for x in out}:out.append(text)
    return out[:12]

def content_prompt(job):
    return f"""Produza conteúdo original em português do Brasil para cadastrar um {job['kind']} WordPress na loja PluginTema.
Produto: {job['product_name']}
Versão: {job['source_version']}
Fonte aprovada: {job['source_url']}
Página oficial confirmada: {job.get('official_url') or 'não confirmada'}
Desenvolvedor confirmado: {job.get('developer') or 'não confirmado'}
Não invente recursos, compatibilidades, desenvolvedor ou URLs. A breve descrição deve ter 400 a 500 caracteres, texto corrido, comercial e informativo, sem versão. A descrição completa deve usar HTML simples. Escolha apenas categorias/tags realmente coerentes.
Responda SOMENTE JSON válido com: product_name, short_description, content, categories (array), tags (array), developer e official_url."""
