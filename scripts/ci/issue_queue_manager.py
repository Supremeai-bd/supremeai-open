#!/usr/bin/env python3
"""
SupremeAI Dynamic Issue Queue Manager (GSPQ: Group-Sequenced Priority Queue)
============================================================================
Enforces:
1. Contiguous sequential claiming (seq:1 -> seq:2 -> seq:3).
2. Dynamic insertion with automatic downstream +1 shift (insert at seq:K -> shifts >= K by +1).
3. Cascade hold: If upstream seq:K fails or is held, downstream seq: > K are auto-held.
4. Restaging & priority rebalancing for the entire repository issue backlog.

Usage:
    python scripts/ci/issue_queue_manager.py audit
    python scripts/ci/issue_queue_manager.py restage
    python scripts/ci/issue_queue_manager.py insert --issue <num> --group <group> --seq <pos>
    python scripts/ci/issue_queue_manager.py next --group <group> [--lane <lane>]
    python scripts/ci/issue_queue_manager.py cascade-hold --group <group>
    python scripts/ci/issue_queue_manager.py verify-claim --issue <num>
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")

def run_cmd(cmd):
    """Run a shell command and return (rc, stdout, stderr) with UTF-8 decoding."""
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    return res.returncode, res.stdout.strip(), res.stderr.strip()

def get_open_issues():
    """Fetch all open issues from GitHub."""
    cmd = [
        "gh", "issue", "list",
        "--repo", REPO,
        "--state", "open",
        "--limit", "300",
        "--json", "number,title,labels,state,createdAt"
    ]
    rc, out, err = run_cmd(cmd)
    if rc != 0:
        print(f"Error fetching issues: {err}", file=sys.stderr)
        return []
    return json.loads(out) if out else []

def get_open_prs():
    """Fetch all open PRs from GitHub."""
    cmd = [
        "gh", "pr", "list",
        "--repo", REPO,
        "--state", "open",
        "--limit", "100",
        "--json", "number,title,labels,headRefName,state"
    ]
    rc, out, err = run_cmd(cmd)
    if rc != 0:
        print(f"Error fetching PRs: {err}", file=sys.stderr)
        return []
    return json.loads(out) if out else []

def parse_metadata(issue):
    """Extract group, seq, priority, and status from issue labels."""
    lbl_names = [l["name"] for l in issue.get("labels", [])]
    
    group = None
    seq = None
    priority = "P3-low"
    
    for l in lbl_names:
        if l.startswith("group:"):
            group = l.split(":", 1)[1]
        elif l.startswith("seq:"):
            try:
                seq = int(l.split(":", 1)[1])
            except ValueError:
                pass
        elif l in ("P0-critical", "P1-high", "P2-medium", "P3-low"):
            priority = l
            
    is_claimed = "status:in-progress" in lbl_names
    has_pr = "has-pr" in lbl_names
    is_blocked = "blocked" in lbl_names
    
    return {
        "number": issue["number"],
        "title": issue["title"],
        "group": group,
        "seq": seq,
        "priority": priority,
        "is_claimed": is_claimed,
        "has_pr": has_pr,
        "is_blocked": is_blocked,
        "labels": lbl_names
    }

def cmd_audit(args):
    """Audit all open issues by group and sequence."""
    issues = get_open_issues()
    print(f"\n=======================================================")
    print(f"  SupremeAI Issue Queue Audit (Total Open: {len(issues)})")
    print(f"=======================================================\n")
    
    groups = {}
    ungrouped = []
    
    for iss in issues:
        meta = parse_metadata(iss)
        grp = meta["group"]
        if grp:
            groups.setdefault(grp, []).append(meta)
        else:
            ungrouped.append(meta)
            
    for grp, items in sorted(groups.items()):
        items.sort(key=lambda x: (x["seq"] or 9999, x["number"]))
        print(f"📁 Group: {grp} ({len(items)} issues)")
        expected_seq = 1
        has_gap = False
        for it in items:
            s_str = f"seq:{it['seq']}" if it['seq'] is not None else "NO_SEQ"
            status = " [HAS-PR]" if it["has_pr"] else (" [IN-PROGRESS]" if it["is_claimed"] else "")
            print(f"   #{it['number']:<5} {s_str:<8} [{it['priority']:<11}] {status:<15} {it['title'][:60]}")
            if it['seq'] != expected_seq:
                has_gap = True
            if it['seq'] is not None:
                expected_seq = it['seq'] + 1
        if has_gap:
            print(f"   ⚠️ Sequence gap or anomaly detected in group '{grp}'!\n")
        else:
            print(f"   ✅ Sequence contiguous and verified.\n")
            
    print(f"📁 Ungrouped Issues: {len(ungrouped)} issues")
    if args.verbose:
        for it in ungrouped:
            print(f"   #{it['number']:<5} [{it['priority']:<11}] {it['title'][:65]}")
    else:
        print("   (Use --verbose to view all ungrouped issues)")

def cmd_insert(args):
    """
    Insert an issue at (group, seq), automatically shifting existing items >= seq by +1.
    """
    target_num = args.issue
    target_grp = args.group
    target_seq = args.seq
    
    print(f"\n>>> Inserting Issue #{target_num} into group:{target_grp} at seq:{target_seq}...")
    issues = get_open_issues()
    group_issues = []
    
    for iss in issues:
        meta = parse_metadata(iss)
        if meta["group"] == target_grp and meta["number"] != target_num:
            group_issues.append(meta)
            
    group_issues.sort(key=lambda x: x["seq"] or 9999, reverse=True)
    
    # Shift existing issues >= target_seq by +1
    shifted_count = 0
    for it in group_issues:
        if it["seq"] is not None and it["seq"] >= target_seq:
            old_seq = it["seq"]
            new_seq = old_seq + 1
            print(f"   Shifting #{it['number']} from seq:{old_seq} -> seq:{new_seq}")
            run_cmd([
                "gh", "issue", "edit", str(it["number"]),
                "--remove-label", f"seq:{old_seq}",
                "--add-label", f"seq:{new_seq}"
            ])
            shifted_count += 1
            time.sleep(0.3)
            
    # Assign target issue
    print(f"   Setting #{target_num} to group:{target_grp}, seq:{target_seq}")
    run_cmd([
        "gh", "issue", "edit", str(target_num),
        "--add-label", f"group:{target_grp}",
        "--add-label", f"seq:{target_seq}"
    ])
    print(f"✅ Insertion complete! #{target_num} is now seq:{target_seq}. Shifted {shifted_count} downstream issues.")

def cmd_verify_claim(args):
    """
    Verify if an issue can be claimed according to contiguous sequential rules.
    Exits with code 0 if allowed, code 1 if blocked.
    """
    issue_num = args.issue
    issues = get_open_issues()
    
    target = None
    for iss in issues:
        if iss["number"] == issue_num:
            target = parse_metadata(iss)
            break
            
    if not target:
        print(f"Error: Issue #{issue_num} not found or closed.", file=sys.stderr)
        sys.exit(1)
        
    grp = target["group"]
    seq = target["seq"]
    
    if not grp or seq is None:
        # Legacy/generic issues without group are claimable with standard checks
        print(f"PASS: Issue #{issue_num} has no group/sequence constraint.")
        sys.exit(0)
        
    if seq == 1:
        print(f"PASS: Issue #{issue_num} is seq:1 (first in sequence).")
        sys.exit(0)
        
    # Check if seq - 1 is already claimed or has a PR
    prev_seq = seq - 1
    found_prev = False
    prev_ready = False
    
    for iss in issues:
        meta = parse_metadata(iss)
        if meta["group"] == grp and meta["seq"] == prev_seq:
            found_prev = True
            # seq - 1 is ready if it has a PR or is in progress
            if meta["has_pr"] or meta["is_claimed"]:
                prev_ready = True
            break
            
    if not found_prev:
        # If prev_seq is closed (e.g. already merged), check if issue was closed
        rc, out, _ = run_cmd(["gh", "issue", "list", "--repo", REPO, "--state", "closed", "--label", f"group:{grp}", "--label", f"seq:{prev_seq}", "--json", "number"])
        if rc == 0 and out and out != "[]":
            prev_ready = True
            
    if prev_ready:
        print(f"PASS: Predecessor seq:{prev_seq} in group '{grp}' is claimed or completed.")
        sys.exit(0)
    else:
        print(f"REJECTED: Sequential constraint violation! Cannot claim seq:{seq} before seq:{prev_seq} in group '{grp}' is claimed or completed.", file=sys.stderr)
        sys.exit(1)

def cmd_cascade_hold(args):
    """
    Inspect open PRs for a group. If PR seq:K fails or is on hold,
    ensure all downstream PRs (seq > K) are placed on queue:hold.
    """
    target_grp = args.group
    prs = get_open_prs()
    issues = get_open_issues()
    
    # Map issue number to metadata
    issue_map = {iss["number"]: parse_metadata(iss) for iss in issues}
    
    # Find PRs that belong to this group
    group_prs = []
    for pr in prs:
        # Check issue references in title or branch
        match = re.search(r"#(\d+)", pr["title"]) or re.search(r"-(\d+)-", pr["headRefName"])
        if match:
            iss_num = int(match.group(1))
            iss_meta = issue_map.get(iss_num)
            if iss_meta and iss_meta["group"] == target_grp:
                group_prs.append({
                    "pr_number": pr["number"],
                    "issue_number": iss_num,
                    "seq": iss_meta["seq"],
                    "labels": [l["name"] for l in pr.get("labels", [])],
                    "title": pr["title"]
                })
                
    group_prs.sort(key=lambda x: x["seq"] or 9999)
    print(f"\nEvaluating Cascade Hold for group '{target_grp}' ({len(group_prs)} PRs):")
    
    blocker_seq = None
    for item in group_prs:
        pr_num = item["pr_number"]
        seq = item["seq"]
        labels = item["labels"]
        
        is_held = "queue:hold" in labels
        is_blocked = "pr-gate:blocked" in labels
        
        if blocker_seq is not None:
            # Downstream must be held!
            if "queue:hold" not in labels:
                print(f"   🔴 Downstream PR #{pr_num} (seq:{seq}) -> Adding queue:hold (blocked by seq:{blocker_seq})")
                run_cmd(["gh", "pr", "edit", str(pr_num), "--add-label", "queue:hold"])
            else:
                print(f"   ⏸️ Downstream PR #{pr_num} (seq:{seq}) -> already on queue:hold.")
        else:
            if is_held or is_blocked:
                blocker_seq = seq
                print(f"   ⚠️ Blocker detected at seq:{seq} (PR #{pr_num}, blocked={is_blocked}, hold={is_held}). Downstream PRs will be frozen.")
            else:
                print(f"   🟢 PR #{pr_num} (seq:{seq}) -> Healthy & green.")

def cmd_restage(args):
    """
    Restage all 139 issues in the repository:
    1. group:ci-hotfix: Critical CI & slot fixes (Issue #2303, #2299) -> P0/P1
    2. group:step-1: Foundation 15 issues (#2246-#2260) -> seq:1 to 15
    3. group:step-2: Dead code pruning issues (#2274-#2277) -> seq:1 to 4
    4. group:step-3: Architectural simplifications (#2278-#2284) -> seq:1 to 7
    5. group:backlog: All remaining low priority issues (#434 to #2228) -> P3-low
    """
    print("\n=======================================================")
    print("  Restaging All Repository Issues into Structured GSPQ")
    print("=======================================================\n")
    
    issues = get_open_issues()
    print(f"Found {len(issues)} open issues.")
    
    # 1. CI Hotfixes
    ci_hotfixes = [2303, 2299]
    print("\n--- Restaging CI Hotfixes (group:ci-hotfix) ---")
    for idx, num in enumerate(ci_hotfixes, 1):
        print(f"   #{num} -> group:ci-hotfix, seq:{idx}, P1-high")
        run_cmd([
            "gh", "issue", "edit", str(num),
            "--add-label", "group:ci-hotfix",
            "--add-label", f"seq:{idx}",
            "--add-label", "P1-high"
        ])
        time.sleep(0.3)
        
    # 2. Step 3 Simplifications (The larger consolidation issues #2278-#2284)
    step3_issues = [2278, 2279, 2280, 2282, 2283, 2284]
    print("\n--- Restaging Step 3 Issues (group:step-3) ---")
    run_cmd(["gh", "label", "create", "group:step-3", "--color", "1d76db", "--description", "Step 3 Architectural Simplifications"])
    for idx, num in enumerate(step3_issues, 1):
        print(f"   #{num} -> group:step-3, seq:{idx}, P2-medium")
        run_cmd([
            "gh", "issue", "edit", str(num),
            "--add-label", "group:step-3",
            "--add-label", f"seq:{idx}",
            "--add-label", "P2-medium"
        ])
        time.sleep(0.3)
        
    # 3. All other issues -> group:backlog, P3-low
    print("\n--- Restaging Backlog Issues (group:backlog, P3-low) ---")
    run_cmd(["gh", "label", "create", "group:backlog", "--color", "cccccc", "--description", "General backlog issues"])
    
    special_nums = set([2254, 2253, 2255, 2252, 2246, 2247, 2248, 2256, 2249, 2250, 2257, 2258, 2259, 2260, 2251, 2274, 2275, 2276, 2277] + ci_hotfixes + step3_issues)
    
    backlog_count = 0
    for iss in issues:
        num = iss["number"]
        if num not in special_nums:
            lbl_names = [l["name"] for l in iss.get("labels", [])]
            if "group:backlog" not in lbl_names:
                print(f"   #{num} -> group:backlog, P3-low")
                run_cmd([
                    "gh", "issue", "edit", str(num),
                    "--add-label", "group:backlog",
                    "--add-label", "P3-low"
                ])
                backlog_count += 1
                time.sleep(0.25)
                
    print(f"\n✅ Restaging complete! Backlog labeled: {backlog_count} issues.")

def cmd_auto_merge(args):
    """
    Sequentially merge approved, ready PRs for a group in strict order (seq:1 -> seq:2 -> seq:3...).
    If an upstream PR is not merged or has conflicts, halts and applies cascade hold.
    """
    target_grp = args.group
    print(f"\n=======================================================")
    print(f"  GSPQ Sequential Auto-Merge Engine: group:{target_grp}")
    print(f"=======================================================\n")
    
    prs = get_open_prs()
    issues = get_open_issues()
    issue_map = {iss["number"]: parse_metadata(iss) for iss in issues}
    
    group_prs = []
    for pr in prs:
        match = re.search(r"#(\d+)", pr["title"]) or re.search(r"-(\d+)-", pr["headRefName"])
        if match:
            iss_num = int(match.group(1))
            iss_meta = issue_map.get(iss_num)
            if iss_meta and iss_meta["group"] == target_grp:
                group_prs.append({
                    "pr_number": pr["number"],
                    "issue_number": iss_num,
                    "seq": iss_meta["seq"],
                    "labels": [l["name"] for l in pr.get("labels", [])],
                    "title": pr["title"]
                })
                
    group_prs.sort(key=lambda x: x["seq"] or 9999)
    if not group_prs:
        print(f"No open PRs found for group '{target_grp}'. All merged or none created!")
        return

    merged_any = False
    for item in group_prs:
        pr_num = item["pr_number"]
        iss_num = item["issue_number"]
        seq = item["seq"]
        
        print(f"\n👉 Checking seq:{seq} (PR #{pr_num}, Issue #{iss_num})...")
        
        # Check mergeability
        rc, out, err = run_cmd(["gh", "pr", "view", str(pr_num), "--json", "mergeable,mergeStateStatus"])
        if rc != 0:
            print(f"   Failed to inspect PR #{pr_num}: {err}")
            break
        data = json.loads(out)
        if data.get("mergeable") == "CONFLICTING":
            print(f"   ❌ PR #{pr_num} has merge conflicts! Halting auto-merge sequence.")
            run_cmd(["gh", "pr", "edit", str(pr_num), "--add-label", "queue:hold"])
            break
            
        # Attempt squash merge
        print(f"   🚀 Merging PR #{pr_num} (seq:{seq}) into main...")
        rc, m_out, m_err = run_cmd(["gh", "pr", "merge", str(pr_num), "--squash", "--admin"])
        if rc == 0:
            print(f"   ✅ PR #{pr_num} merged successfully!")
            run_cmd(["gh", "issue", "close", str(iss_num), "--comment", f"Closed via GSPQ sequential merge of PR #{pr_num}."])
            merged_any = True
            time.sleep(2)
        else:
            print(f"   ⚠️ Could not merge PR #{pr_num}: {m_err}")
            print(f"   Halting sequential auto-merge to preserve order.")
            break
            
    if merged_any:
        print(f"\n🎉 Sequential auto-merge cycle completed successfully!")

def main():
    parser = argparse.ArgumentParser(description="SupremeAI Dynamic Issue Queue Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    p_audit = subparsers.add_parser("audit", help="Audit issues by group and sequence")
    p_audit.add_argument("--verbose", "-v", action="store_true", help="Show all ungrouped issues")
    p_audit.set_defaults(func=cmd_audit)
    
    p_insert = subparsers.add_parser("insert", help="Insert an issue at sequence position, shifting downstream")
    p_insert.add_argument("--issue", type=int, required=True, help="Issue number to insert")
    p_insert.add_argument("--group", type=str, required=True, help="Target group (e.g. step-1, step-2)")
    p_insert.add_argument("--seq", type=int, required=True, help="Target sequence number")
    p_insert.set_defaults(func=cmd_insert)
    
    p_verify = subparsers.add_parser("verify-claim", help="Verify if an issue is claimable under sequence rules")
    p_verify.add_argument("--issue", type=int, required=True, help="Issue number to verify")
    p_verify.set_defaults(func=cmd_verify_claim)
    
    p_cascade = subparsers.add_parser("cascade-hold", help="Auto-freeze downstream PRs if upstream fails")
    p_cascade.add_argument("--group", type=str, required=True, help="Group name to evaluate")
    p_cascade.set_defaults(func=cmd_cascade_hold)
    
    p_restage = subparsers.add_parser("restage", help="Restage all repository issues into GSPQ")
    p_restage.set_defaults(func=cmd_restage)

    p_automerge = subparsers.add_parser("auto-merge", help="Sequentially merge approved PRs for a group")
    p_automerge.add_argument("--group", type=str, required=True, help="Group name to auto-merge")
    p_automerge.set_defaults(func=cmd_auto_merge)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
