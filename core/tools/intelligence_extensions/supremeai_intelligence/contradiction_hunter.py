from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

Query=Callable[[str,int],Awaitable[list[dict[str,Any]]]]
Judge=Callable[[str,str],Awaitable[tuple[bool,float,str]]]
@dataclass
class ContradictionReport:
    candidate_id:str; contradictions:list[dict]=field(default_factory=list); duplicates:list[str]=field(default_factory=list)
    @property
    def safe_to_promote(self): return not self.contradictions
class ContradictionHunter:
    def __init__(self,memory_query:Query,contradiction_judge:Judge|None=None,top_k=10,block=.75): self.q=memory_query; self.j=contradiction_judge; self.k=top_k; self.block=block
    async def inspect(self,candidate_id,content):
        import asyncio
        rows=await self.q(content,self.k); c=[]; d=[]
        async def one(m):
            mid=str(m.get('memory_id') or m.get('session_id') or ''); old=str(m.get('content') or m.get('summary') or '')
            if not old:return
            if self.j:
                bad,score,why=await self.j(content,old)
                if bad and score>=self.block:c.append({'memory_id':mid,'score':score,'rationale':why})
                elif score>=.9:d.append(mid)
            else:
                a=set(content.lower().split()); b=set(old.lower().split()); overlap=len(a&b)/max(1,len(a|b))
                if overlap>=.9:d.append(mid)
        await asyncio.gather(*(one(m) for m in rows)); return ContradictionReport(candidate_id,c,sorted({x for x in d if x}))
