from __future__ import annotations

import re


def safe_message(error: BaseException) -> str:
    text=str(error).replace("\r"," ").replace("\n"," ")
    text=re.sub(r"(?i)(password|secret|token|authorization|cookie)=?\s*[^ ]+",r"\1=[redacted]",text)
    return text[:1000]
