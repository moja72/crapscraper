from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class SyncSelection:
    selection_id:str
    catalog_id:str
    catalog_label:str
    role:str
    product:dict[str,Any]
    source_provider:str=""
    def to_dict(self):return {"selection_id":self.selection_id,"catalog_id":self.catalog_id,"catalog_label":self.catalog_label,"role":self.role,"source_provider":self.source_provider,**self.product}
