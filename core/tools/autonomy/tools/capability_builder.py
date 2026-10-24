from __future__ import annotations

import argparse
from pathlib import Path

from common import json_dump, walk_files

KEYWORDS={
 'web_app':['browser','frontend','ui','next.js','react','website'],
 'api':['api','endpoint','rest','graphql','webhook'],
 'data':['database','postgres','sqlite','sql','etl','analytics'],
 'ai':['llm','embedding','rag','agent','prompt','model','vector'],
 'devops':['deploy','ci','cd','docker','kubernetes','terraform'],
 'automation':['queue','cron','worker','workflow','schedule'],
}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('project'); ap.add_argument('--goal',required=True); ap.add_argument('--output',default='reports/capability_plan.json'); a=ap.parse_args(); root=Path(a.project).resolve(); files=[p.name.lower() for p in walk_files(root)][:5000]
    g=a.goal.lower(); likely=[k for k,v in KEYWORDS.items() if any(x in g for x in v)]
    capabilities=[]
    for k in likely or ['general']:
        capabilities.append({'capability':k,'status':'discover_required','suggested_tools':['code_search','tests','runtime_observability','documentation'],'approval':'human_for_external_side_effects'})
    result={'goal':a.goal,'inferred_domains':likely,'capability_plan':capabilities,'principle':'compose existing tools before inventing new services','project_file_sample_size':len(files)}
    json_dump(result,Path(a.output))
if __name__=='__main__': main()
