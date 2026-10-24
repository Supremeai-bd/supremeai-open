from collections import defaultdict
from dataclasses import dataclass


@dataclass
class SkillCandidate:
    name:str; trigger:str; steps:list[str]; preconditions:list[str]; postconditions:list[str]; evidence_ids:list[str]; confidence:float; version:str='0.1.0'
class SkillDistiller:
    def __init__(self,min_successes=3,min_confidence=.75):self.min_successes=min_successes;self.min_confidence=min_confidence
    def distill(self,workflows):
        groups=defaultdict(list)
        for w in workflows:
            if w.get('success'):groups[str(w.get('signature') or w.get('task_type') or 'general')].append(w)
        out=[]
        for sig,items in groups.items():
            if len(items)<self.min_successes:continue
            counts=defaultdict(int)
            for w in items:
                for s in w.get('steps',[]):counts[str(s)]+=1
            steps=[s for s,c in counts.items() if c>=max(2,len(items)//2)]; conf=sum(float(w.get('quality',.8)) for w in items)/len(items)
            if conf<self.min_confidence:continue
            out.append(SkillCandidate(f'distilled_{sig.lower().replace(" ","_")}',sig,steps,[],[],[str(w.get('execution_id')) for w in items if w.get('execution_id')],conf))
        return out
