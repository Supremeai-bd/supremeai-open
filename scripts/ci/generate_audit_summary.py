import os

def generate_summary():
    report_dir = "ci-reports"
    summary_file = os.path.join(report_dir, "summary.txt")
    errors_file = os.path.join(report_dir, "errors.txt")
    warnings_file = os.path.join(report_dir, "warnings.txt")

    summary_md = ["# 🛡️ SupremeAI CI Audit Report\n"]

    def read_lines(filepath):
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        return []

    passed = read_lines(summary_file)
    errors = read_lines(errors_file)
    warnings = read_lines(warnings_file)

    if errors:
        summary_md.append("### ❌ Status: **FAILED**")
    elif warnings:
        summary_md.append("### ⚠️ Status: **PASSED WITH WARNINGS**")
    else:
        summary_md.append("### ✅ Status: **PASSED**")

    summary_md.append("\n---\n")

    summary_md.append("| Metric | Count |")
    summary_md.append("|--------|-------|")
    summary_md.append(f"| ✅ Passed Checks | {len(passed)} |")
    summary_md.append(f"| ⚠️ Warnings | {len(warnings)} |")
    summary_md.append(f"| ❌ Errors | {len(errors)} |\n")

    if errors:
        summary_md.append("### ❌ Critical Errors")
        summary_md.append("```text")
        for e in errors:
            summary_md.append(e)
        summary_md.append("```\n")

    if warnings:
        summary_md.append("### ⚠️ Warnings")
        summary_md.append("<details><summary>Click to view warnings</summary>\n")
        summary_md.append("```text")
        for w in warnings:
            summary_md.append(w)
        summary_md.append("```\n")
        summary_md.append("</details>\n")

    if passed:
        summary_md.append("### ✅ Successful Checks")
        summary_md.append("<details><summary>Click to view passed checks</summary>\n")
        for p in passed:
            summary_md.append(f"- {p.replace('PASS: ', '')}")
        summary_md.append("\n</details>\n")

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write("\n".join(summary_md) + "\n")
    else:
        print("\n".join(summary_md))

if __name__ == "__main__":
    generate_summary()
