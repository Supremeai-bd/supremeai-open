from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .contracts import SourceRecord

Resolver=Callable[[str],Awaitable[list[SourceRecord]]]
Judge=Callable[[str,list[SourceRecord]],Awaitable[tuple[str,float,str]]]
@dataclass
class EvidenceReport:
    claim:str; status:str; score:float; sources:list[SourceRecord]=field(default_factory=list); rationale:str=''
    @property
    def verified(self): return self.status=='supported' and self.score>=.7 and bool(self.sources)
class EvidenceVerifier:
    def __init__(self,source_resolver:Resolver,claim_judge:Judge|None=None,min_score=.7): self.r=source_resolver; self.j=claim_judge; self.min=min_score
    async def verify_one(self,claim):
        s=await self.r(claim)
        if not s:return EvidenceReport(claim,'unsupported',0,[], 'No evidence returned.')
        if self.j: status,score,why=await self.j(claim,s)
        else: score=sum(max(0,min(1,x.reliability)) for x in s)/len(s); status='supported' if score>=self.min else 'conflicting'; why='Weighted source reliability heuristic.'
        return EvidenceReport(claim,status,score,s,why)
    async def verify(self,claims):
        import asyncio
        return await asyncio.gather(*(self.verify_one(c) for c in claims))
