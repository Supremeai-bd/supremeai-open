import asyncio
from datetime import datetime, timezone


class KnowledgeRevalidator:
    DEFAULT={'pricing':3,'software-api':14,'models':7,'regulation':7,'security':14,'general':90}
    def __init__(self,recheck,ttls=None,max_concurrency=8): self.recheck=recheck; self.ttl={**self.DEFAULT,**(ttls or {})}; self.sem=asyncio.Semaphore(max_concurrency)
    def due(self,m,now=None):
        now=now or datetime.now(timezone.utc); ts=m.get('last_verified_at') or m.get('updated_at') or m.get('created_at')
        if not ts:return True
        try:dt=datetime.fromisoformat(ts.replace('Z','+00:00'))
        except ValueError:return True
        return (now-dt).total_seconds()>=self.ttl.get(m.get('domain','general'),90)*86400
    async def revalidate(self,memories):
        async def one(m):
            async with self.sem:
                if not self.due(m):return {'memory_id':m.get('memory_id'),'status':'not_due'}
                try:r=await self.recheck(m); r.setdefault('memory_id',m.get('memory_id')); r['revalidated_at']=datetime.now(timezone.utc).isoformat(); return r
                except Exception as e:return {'memory_id':m.get('memory_id'),'status':'error','error':str(e)}
        return await asyncio.gather(*(one(m) for m in memories))
