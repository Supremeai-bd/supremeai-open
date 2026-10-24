from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path

from common import json_dump


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--source',required=True); ap.add_argument('--title',required=True); ap.add_argument('--authority',type=float,default=.8); ap.add_argument('--output',default='reports/knowledge_record.json'); a=ap.parse_args(); text=Path(a.source).read_text(encoding='utf-8',errors='replace')
    record={'id':'kn_'+hashlib.sha256(text.encode()).hexdigest()[:16],'title':a.title,'source':a.source,'authority':a.authority,'ingested_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'content_sha256':hashlib.sha256(text.encode()).hexdigest(),'claims':[line.strip() for line in text.splitlines() if line.strip()][:100],'provenance':{'source_file':a.source,'derived_by':'knowledge_ingestor'}}
    json_dump(record,Path(a.output))
if __name__=='__main__': main()
