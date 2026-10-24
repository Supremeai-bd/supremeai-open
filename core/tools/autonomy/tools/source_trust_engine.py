from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import json_dump


def score(item):
    authority=float(item.get('authority',0)); freshness=float(item.get('freshness',0)); provenance=float(item.get('provenance',0)); corroboration=float(item.get('corroboration',0)); conflicts=float(item.get('conflicts',0))
    return round(max(0,min(100,35*authority+20*freshness+20*provenance+15*corroboration-25*conflicts)),2)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output',default='reports/source_trust.json'); a=ap.parse_args(); data=json.loads(Path(a.input).read_text(encoding='utf-8'))
    sources=[]
    for s in data.get('sources',data if isinstance(data,list) else []):
        x=dict(s); x['trust_score']=score(x); x['decision']='accept' if x['trust_score']>=75 and x.get('conflicts',0)<0.2 else ('review' if x['trust_score']>=50 else 'reject'); sources.append(x)
    sources.sort(key=lambda x:x['trust_score'],reverse=True); json_dump({'sources':sources,'policy':{'require_primary_or_official_for_factual_claims':True,'require_corroboration_for_high_impact_changes':True,'store_provenance':True}},Path(a.output))
if __name__=='__main__': main()
