from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def now(): return datetime.now(timezone.utc).isoformat()
@dataclass
class SourceRecord:
    source_id:str; source_type:str; title:str=''; url:str=''; content:str=''; published_at:str|None=None; observed_at:str=field(default_factory=now); reliability:float=.5; metadata:dict[str,Any]=field(default_factory=dict)
