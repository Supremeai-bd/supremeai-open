from __future__ import annotations

import argparse
from pathlib import Path

from common import json_dump

LEVELS=['LOW','MEDIUM','HIGH','CRITICAL']
def classify(files, external=False, data_migration=False, auth=False, production=False):
    score=0
    score += min(6,len(files)//3)
    score += 3 if external else 0
    score += 4 if data_migration else 0
    score += 4 if auth else 0
    score += 3 if production else 0
    level='LOW' if score<=2 else 'MEDIUM' if score<=5 else 'HIGH' if score<=9 else 'CRITICAL'
    return score,level

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--files',nargs='*',default=[]); ap.add_argument('--external',action='store_true'); ap.add_argument('--data-migration',action='store_true'); ap.add_argument('--auth',action='store_true'); ap.add_argument('--production',action='store_true'); ap.add_argument('--output',default='reports/change_budget.json'); a=ap.parse_args(); score,level=classify(a.files,a.external,a.data_migration,a.auth,a.production)
    result={'score':score,'level':level,'allowed_mode':'auto' if level=='LOW' else 'supervised' if level in {'MEDIUM','HIGH'} else 'human_approval','controls':['small diff first','tests before merge','rollback path required','no secret exfiltration','no irreversible production action without explicit approval']}
    json_dump(result,Path(a.output))
if __name__=='__main__': main()
