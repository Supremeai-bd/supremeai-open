import re

failed_files = set()
with open("pytest_full_run_results.txt", encoding="utf-16-le", errors="ignore") as f:
    for line in f:
        line = line.strip()
        if line.startswith("FAILED ") or line.startswith("ERROR "):
            parts = line.split(" ", 1)[1].split("::")
            file_path = parts[0]
            file_name = file_path.split("/")[-1]
            failed_files.add(file_name)

md_path = r"c:\Users\n\supremeai\supremeai_2.0\docs\quality\test_coverage_plan.md"
with open(md_path, encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
in_table = False
for line in lines:
    if line.strip().startswith("|") and "ফাইল" in line and "স্ট্যাটাস" in line:
        in_table = True
        new_lines.append(line)
        continue

    if in_table and line.strip().startswith("|---"):
        new_lines.append(line)
        continue

    if in_table and not line.strip().startswith("|"):
        in_table = False
        new_lines.append(line)
        continue

    if in_table and line.strip().startswith("|"):
        parts = line.split("|")
        if len(parts) >= 4:
            # We look for a markdown backtick code block that ends with .py
            m = re.search(r"`([^`]+\.py)`", parts[2])
            if m:
                filename = m.group(1).split("/")[-1]
                if filename in failed_files:
                    parts[-2] = " ⚠️ ফেইল "
                else:
                    parts[-2] = " ✅ পাস "
                line = "|".join(parts)
        new_lines.append(line)
    else:
        new_lines.append(line)

with open(md_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
