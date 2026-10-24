import os
import shutil

plans_base = r'f:\supremeai\docs\plans'

for f in os.listdir(plans_base):
    fp = os.path.join(plans_base, f)
    if os.path.isfile(fp):
        if any(ord(c) > 127 for c in f):
            with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                content = fh.read(1000)

            # Check content to rename properly
            if 'কাজের পরিকল্পনা' in content or 'work plan' in content.lower():
                dst = os.path.join(plans_base, 'features', 'supremeai_work_plan_bangla.md')
            elif 'সম্পূর্ণ পরিচিতি' in content or 'overview' in content.lower():
                dst = os.path.join(plans_base, 'architecture', 'supremeai_project_complete_overview_bangla.md')
            else:
                dst = os.path.join(plans_base, 'features', 'supremeai_bangla_specification.md')

            shutil.move(fp, dst)

print('Moved all non-ascii root files successfully.')
