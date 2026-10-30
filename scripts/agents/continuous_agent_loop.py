diff --git a/scripts/agents/continuous_agent_loop.py b/scripts/agents/continuous_agent_loop.py
index 3f7c863..3c473ab 100644
--- a/scripts/agents/continuous_agent_loop.py
+++ b/scripts/agents/continuous_agent_loop.py
@@ -1490,6 +1490,41 @@ def pre_work_rebase_guard() -> tuple[bool, int, str]:
 # চালায় না। সৎ pre-push/pre-work rebase গার্ড (#161, #514) অক্ষত রাখা হলো —
 # এরা সত্যিকারের কাজ করে; ভবিষ্যতে বাস্তব কনজিউমার এলে সরাসরি wire করা যাবে।
 
+# বাংলা: বোর্ডের নিজস্ব টাইটেল-কনভেনশন — "verb(scope):" প্রিফিক্স রো-এর প্রকৃত
+# লেন নির্দেশ করে। লাইভ প্রমাণ 2026-10-30T11:19Z: #2529 "audit(federation): P0
+# #2511 RCA verified …" (labels: []) রো-টি role=coder + task_type=IMPLEMENT
+# এনভেলপে ডিসপ্যাচ হয়েছিল, অথচ রো-টির নিজের বডিই ঘোষণা করে "Audit (auditor
+# envelope, evidence-only, zero fixes attempted)"। ফলাফল: একটি প্রমাণ-রিসিপ্ট রো
+# বাস্তবায়ন-টাস্ক হিসেবে ডিসপ্যাচ হয়ে এজেন্ট-সাইকেল নষ্ট হয় — ঠিক সেই অপচয়-শ্রেণি
+# যেটা stale-incident/stale-claim গার্ডরা ঠেকাতে চায় (root-cause fix: এক বার
+# শ্রেণিবিন্যাস ঠিক, প্রতি-রো প্যাচ নয়)। লেবেল-সংকেত (status:runway,
+# gate:pre-landing) আগে চলে — টাইটেল-প্রিফিক্স শুধু অবশিষ্ট ক্ষেত্রে ম্যাপ করে,
+# তাই fix(ci)+status:runway আজও ci-fixer পায়। অ্যানকমন প্রিফিক্স (fix/feat/chore
+# …) অ-ম্যাপড → পুরোনো লজিক অপরিবর্তিত।
+EVIDENCE_LANE_TITLE_ROLES: dict[str, str] = {
+    "audit": "task-auditor",
+    "report": "task-auditor",
+    "triage": "task-auditor",
+    "verify": "task-auditor",
+    "census": "task-auditor",
+    "ops": "task-auditor",
+    "dispatch": "task-auditor",
+    "guard": "platform-guardian",
+    "sentry": "platform-guardian",
+    "scout": "ecosystem-scout",
+}
+
+# বাংলা: envelope-এর task_type এখন role-থেকে সৎভাবে নেওয়া হয় — প্রমাণ-লেন রো
+# আর "IMPLEMENT" ভুখণ্ড পায় না (SPEC §2 task_type রেজিস্ট্রি: AUDIT/SCOUT/OPS/FIX)।
+ROLE_TASK_TYPES: dict[str, str] = {
+    "task-auditor": "AUDIT",
+    "auditor": "AUDIT",
+    "ecosystem-scout": "SCOUT",
+    "platform-guardian": "OPS",
+    "ci-fixer": "FIX",
+}
+
+
 def classify_task_role(
     title: str = "", labels: Iterable[str] = (), body: str = ""
 ) -> str:
@@ -1498,6 +1533,17 @@ def classify_task_role(
         return "ci-fixer"
     if "gate:pre-landing" in present:
         return "task-auditor"
+    # বাংলা: টাইটেল-প্রিফিক্স ম্যাপ — বোর্ডের "verb(scope):" কনভেনশন রো-এর লেন
+    # ঘোষণা করে; প্রথম টোকেন case-insensitive ম্যাচ (EVIDENCE_LANE_TITLE_ROLES)।
+    # কঠোর আকৃতি: টোকেনের পরে (ঐচ্ছিক স্পেস সহ) `(` বা `:` থাকতে হবে — কীওয়ার্ড
+    # বাক্য নয়। #489 চুক্তি: "audit readiness report"-জাতীয় কীওয়ার্ড-টাইটেল আর
+    # role আবিষ্কার করতে পারে না — সেরা coder ডিফল্টেই যায় (Tier3 রিগ্রেশন
+    # চুক্তি, tests/test_self_healing_reporter.py::test_loop_module_healthy…)।
+    head = str(title or "").lstrip().lower()
+    token_match = re.match(r"([a-z][a-z-]*)\s*[:(]", head)
+    mapped = EVIDENCE_LANE_TITLE_ROLES.get(token_match.group(1)) if token_match else None
+    if mapped is not None:
+        return mapped
     if "status:claimed" in present:
         return "coder"
     return "coder"
@@ -1566,6 +1612,12 @@ def build_task_envelope(
             log("!", f"[Envelope] unknown --role '{role_override}'; falling back to classified role '{classified}'")
             role = classified
 
+    # বাংলা: task_type এখন final role থেকে সৎ derivation (role_override-সহ) —
+    # প্রমাণ-লেন রো (audit/report/triage/verify/guard/scout টাইটেল) আর IMPLEMENT
+    # ভুখণ্ড পায় না (লাইভ #2529 মিস-ডিসপ্যাচ, 2026-10-30T11:19Z)। অজানা role →
+    # আগের আচরণ (IMPLEMENT)।
+    task_type = ROLE_TASK_TYPES.get(role, "IMPLEMENT")
+
     role_description = ROLE_RULES.get(
         role,
         ROLE_RULES["solver"] if role in ("coder", "solver") else "Execute role objectives strictly.",
@@ -1595,7 +1647,7 @@ def build_task_envelope(
         "output_format": "task-envelope-v1",
         "task_id": f"task-{issue_number}" if issue_number else "task-adhoc",
         "issue": issue_number,
-        "task_type": "IMPLEMENT",
+        "task_type": task_type,
         "group": resolved_group,
         "priority": _detect_priority(labels),
         "objective": title or ("Ad-hoc task — objective supplied by the calling agent." if not issue_number else ""),
@@ -2084,11 +2136,17 @@ def run_dispatch_cycle(args: argparse.Namespace) -> int:
             # claim-first mandate অপরিবর্তিত (#1530-র zero-dispatch-change শৃঙ্খলা)।
             picked_issue = next((i for i in raw if str(i.get("number")) == picked), None)
             picked_labels = []
-            if isinstance(picked_issue, dict) and isinstance(picked_issue.get("labels"), list):
-                picked_labels = [
-                    str(l.get("name", "")).lower() for l in picked_issue["labels"] if isinstance(l, dict)
-                ]
-            classified = classify_task_role(labels=picked_labels)
+            picked_title = ""
+            if isinstance(picked_issue, dict):
+                # বাংলা: টাইটেলও প্রেরণ — classify_task_role-এর নতুন টাইটেল-প্রিফিক্স
+                # ম্যাপ (audit(/report(/guard(/scout(…) dispatch-পথেও কাজ করে; আগে
+                # labels-only কলে প্রমাণ-রিসিপ্ট রো coder-শ্রেণি হত।
+                picked_title = str(picked_issue.get("title", "") or "")
+                if isinstance(picked_issue.get("labels"), list):
+                    picked_labels = [
+                        str(l.get("name", "")).lower() for l in picked_issue["labels"] if isinstance(l, dict)
+                    ]
+            classified = classify_task_role(title=picked_title, labels=picked_labels)
             dispatch_role = args.role or "solver"
             if args.role and args.role not in SPECIALIST_ROLES and args.role not in ROLE_RULES:
                 log("!", f"unknown --role '{args.role}'; dispatching as solver")
