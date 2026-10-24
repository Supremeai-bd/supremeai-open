import json
import re

path = 'coldstart_knowledge_seed_knowledge_base.json'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: [[" -> ["  (extra opening brackets at start of array)
content = content.replace('[[', '[')

# Fix 2: , [" -> , "  (extra opening brackets mid-array — string starts with [)
content = re.sub(r',\s*\["', ', "', content)

# Fix 3: "]] at end of value strings where closing quote is missing
# Pattern: text]] should be text"]  — word chars followed by ]]
# But NOT ]] that closes array structure (which follows a ")
# So look for: (word or space) ]] where preceded by non-" character
content = re.sub(r'(\w)\s*\]\]', r'\1"', content)

# Fix 4: ]] that properly closes (after ") -> single ]
# e.g. "text"]] -> "text"]
content = re.sub(r'"\]\]', '"]', content)

# Fix 5: any remaining ]] -> ]
content = content.replace(']]', ']')

# Fix 6: any remaining [[ -> [
content = content.replace('[[', '[')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

try:
    data = json.loads(content)
    cats = data['categories']
    total = sum(len(c['entries']) for c in cats)
    print(f'JSON is VALID. Schema v={data["schema_version"]}, categories={len(cats)}, total_entries={total}')
    for c in cats:
        print(f'  {c["category_id"]}: {len(c["entries"])} entries, domain={c["domain"]}')
except json.JSONDecodeError as e:
    print(f'Still broken: {e}')
    lines = content.split('\n')
    print(f'Line {e.lineno}: {lines[e.lineno-1][:200]}')
