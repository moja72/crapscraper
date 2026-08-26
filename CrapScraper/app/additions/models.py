from __future__ import annotations
from dataclasses import asdict,dataclass,field
from datetime import datetime,timezone
from typing import Any

def utc_now():return datetime.now(timezone.utc).isoformat(timespec="seconds")

@dataclass
class AdditionError:
    message:str;technical_message:str="";code:str="addition_error";stage:str="";source:str="";attempt_id:str="";job_id:str="";timestamp:str=field(default_factory=utc_now);recoverable:bool=True
    def to_dict(self)->dict[str,Any]:return asdict(self)

PUBLIC_STATES=("ready","running","success","error")
