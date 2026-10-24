from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class MemoryDecision:
    action:str; memory_id:str; reason:str; score:float
class MemoryCurator:
    def __init__(self,promote=.78,demote=.45,archive=.25,ttl=None): self.promote=promote; self.demote=demote; self.archive=archive; self.ttl={'general':180,'pricing':7,'software-api':30,'models':14,'regulation':14,**(ttl or {})}
    def decide(self,m):
        mid=str(m.get('memory_id') or m.get('session_id') or ''); s=float(m.get('confidence',m.get('score',0)) or 0); status=m.get('verification_status','unverified')
        if self.expired(m):return MemoryDecision('expire',mid,'TTL elapsed',s)
        if status=='verified' and s>=self.promote:return MemoryDecision('promote',mid,'Verified and high confidence',s)
        if s>=self.demote:return MemoryDecision('retain',mid,'Usable but not promotable',s)
        if s>=self.archive:return MemoryDecision('archive',mid,'Low confidence',s)
        return MemoryDecision('demote',mid,'Very low confidence',s)
    def expired(self,m):
        ts=m.get('expires_at') or m.get('created_at');
        if not ts:return False
        try:dt=datetime.fromisoformat(ts.replace('Z','+00:00'))
        except ValueError:return False
        if m.get('expires_at'):return dt<=datetime.now(timezone.utc)
        return dt+timedelta(days=self.ttl.get(m.get('domain','general'),180))<=datetime.now(timezone.utc)
    def merge(self,a,b):
        out=dict(a); out['confidence']=max(float(a.get('confidence',0)),float(b.get('confidence',0))); out['tags']=sorted(set(a.get('tags',[]))|set(b.get('tags',[]))); out['provenance']=a.get('provenance',[])+b.get('provenance',[]); return out
