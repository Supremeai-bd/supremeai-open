import hashlib
import re
from dataclasses import dataclass, field


@dataclass
class FailurePattern:
    fingerprint:str; category:str; signature:str; recurrence:int; examples:list[str]=field(default_factory=list); prevention_rules:list[str]=field(default_factory=list); severity:str='medium'
class FailurePatternMiner:
    NOISE=re.compile(r'(0x[0-9a-f]+|\d+|[0-9a-f]{8,})',re.IGNORECASE)
    def fingerprint(self,text,category='unknown'):
        norm=self.NOISE.sub('<N>',text.lower()); norm=re.sub(r'\s+',' ',norm).strip(); return hashlib.sha256(f'{category}|{norm[:1200]}'.encode()).hexdigest()[:20]
    def mine(self,failures):
        g={}
        for x in failures:
            text=str(x.get('message') or x.get('error') or x.get('content') or ''); cat=str(x.get('category','unknown'))
            if not text:continue
            fp=self.fingerprint(text,cat); p=g.setdefault(fp,FailurePattern(fp,cat,self.NOISE.sub('<N>',text.lower())[:500],0,[],[],str(x.get('severity','medium')))); p.recurrence+=1; p.examples=(p.examples+[text[:800]])[:5]
        for p in g.values():
            t=f'{p.category} {p.signature}'; p.prevention_rules=['Add bounded timeout/retry/circuit-breaker coverage.' if 'timeout' in t else 'Create a regression test and record the trigger.']
        return sorted(g.values(),key=lambda x:x.recurrence,reverse=True)
