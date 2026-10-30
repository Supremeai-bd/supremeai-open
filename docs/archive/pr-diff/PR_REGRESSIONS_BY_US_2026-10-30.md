# আমাদের করা Regression তালিকা (Merged PRs in main)

> উৎস: `F:\pr diff\pr_incident_index.json` + সংশ্লিষ্ট diff ফাইল।  
> স্কোপ: `main`-এ merge হওয়া PR যেগুলো পরবর্তীতে আমাদেরই আরেকটি PR দিয়ে "regression/breakage" হিসেবে চিহ্নিত ও ঠিক করা হয়েছে।  
> তারিখ: 2026-10-30

## পদ্ধতি (Method)

1. `pr_incident_index.json`-এর 1335টি merged PR record পড়া হয়েছে।
2. প্রতিটি fix/restore/rescue PR-এর `title` + `reflection_why` থেকে কারণসূত্র (causal link) বের করা হয়েছে — যেখানে স্পষ্টভাবে উল্লেখ আছে যে একটি আগের PR/landing কোনো কাজ ভেঙেছে/হারিয়েছে/severed করেছে।
3. শুধু সেই PR-গুলোকে "regression made by us" হিসেবে গণ্য করা হয়েছে যেগুলো `main`-এ merged এবং পরবর্তী fix PR দ্বারা সরাসরি চিহ্নিত।
4. শুধু cleanup/follow-up (যেমন leftover reference সরানো) গণ্য করা হয়নি।

## নিশ্চিত regression-causing PR (Confirmed)

| # | Regression-causing PR | কী ভেঙেছিল / হারিয়েছিল | Fix PR(s) | এলাকা |
|---|---|---|---|---|
| 1 | **#153** — `refactor(mcp-tower): route redactDiagnostic through masking.ts SSOT` | #112 type dedupe merge race-এ হারিয়ে গিয়েছিল | #159 | mcp-tower |
| 2 | **#660** — loop chokepoint hang + board failures masquerade as empty board | #567 constitution freshness gate regressed | #687 | agent-loop |
| 3 | **#860 / #866** — Cosmic landing (public landing page at `/` + phases) | Cosmic landing PR router-কে marketing-only router দিয়ে প্রতিস্থাপন করে login/register + authenticated app মেরে ফেলেছিল | #877, #881, #891 | studio (App.tsx router) |
| 4 | **#1042** — `fix(api): calibrate secret-scan patterns` | sanctioned Render service ID default + scan gate breakage introduced | #1045 | api / secret-scan |
| 5 | **#1190** — Mobile Simulator both-ways feature | BrowserPreview real-browser upgrade + manual-work-UI removal merge regression; toolbar/perks হারিয়েছিল | #1196 | studio (BrowserPreview) |
| 6 | **#1526** — 60-line minimal autonomous loop | machine path severed: `--task-envelope` stub, freshness gate freeze, dispatch filter divergence, CONTRACT_VERSION duplicate | #1535, #1539, #1544 | core/loop |
| 7 | **Bangla-first role-brief rewrite** (offending PR number index-এ সরাসরি চিহ্নিত নয়) | ecosystem-scout grounding discipline (anti-speculation clause) drop করেছিল | #1878 | loop / scout |
| 8 | **#1247** — `fix(studio): add 200! force rewrite for /admin` | stale edge-redirect fix-এর পর code-level reference cleanup বাকি রেখেছিল (partial) | #1251 | studio / CORS |

## বাংলা ব্যাখ্যা (সহজ ভাষায়)

1. **#153** — MCP tower-এর redactDiagnostic masking SSOT refactor merge race-এ #112-এর type dedupe হারিয়ে গিয়েছিল; #159-এ restore করা হয়।
2. **#660** — loop chokepoint hang fix করতে গিয়ে #567-এর constitution freshness gate regressed হয়েছিল; #687-এ restore।
3. **#860/#866** — Cosmic landing PR App.tsx router-কে marketing-only router দিয়ে বদলে দিয়েছিল, ফলে login/register ও authenticated app মরে গিয়েছিল; #877/#881/#891-এ full router restore।
4. **#1042** — secret-scan calibration PR-এ sanctioned Render service ID default + scan gate breakage introduced; #1045-এ suppress/fix।
5. **#1190** — Mobile Simulator feature merge-এ BrowserPreview-এর real-browser upgrade + manual-work-UI removal regression হয়েছিল; #1196-এ restore।
6. **#1526** — 60-line minimal loop rewrite machine contract (task-envelope, freshness gate, dispatch filter) severed করেছিল; #1535/#1539/#1544-এ heal।
7. **role-brief rewrite (PR # অজানা)** — Bangla-first brief rewrite ecosystem-scout-এর anti-speculation guard drop করেছিল; #1878-এ restore।
8. **#1247** — `/admin` force rewrite fix leftover code-level deprecated host references রেখেছিল; #1251-এ cleanup (partial, functional regression নয়)।

## লক্ষ্য (Notes)

- উপরের তালিকা শুধু সেই PR-গুলো যেগুলো পরবর্তী fix PR দ্বারা **সরাসরি** regression/breakage হিসেবে চিহ্নিত।
- অন্যান্য fix/restore PR (যেমন #1064 missing service files, #1201 DecisionEngine contract, #1234 button contract, #1099 SecureStore, #1245 AdminShell route, #1576 while-loop revert, #997 memory sidecar) তাদের offending PR index-এ সরাসরি চিহ্নিত নয় বা issue-level reference (যেমন #761, #2734, #1896) ব্যবহার করেছে; সেগুলো আলাদা audit-এ চাইলে যোগ করা যাবে।
- এই ডকুমেন্ট শুধু তথ্যমূলক; কোনো কোড পরিবর্তন করা হয়নি।
