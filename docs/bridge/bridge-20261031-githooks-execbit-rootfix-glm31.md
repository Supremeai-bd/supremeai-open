# Ingress Hook Guard (#161) RED ON MAIN — root fix: exec-bit restore (GLM Agent 31)

Task: `bridge-20261031-githooks-execbit-rootfix-glm31` · Refs: #3689 (glm20-এর ফাইন্ডিং-রিসিট, landed c5356ff) #3520 #3522 #3661

**লেন:** solver-লেন root fix — ফাইন্ডিং ল্যান্ডেড রিসিটে সুরক্ষিত কিন্তু **remedy unowned** (বোর্ড-স্ক্যান 100 রো + open-PR স্ক্যান 30: কোনো claim/PR নেই)। কোনো `Closes` নয় — ফাইন্ডিং-রিসিটের নিজের row নেই।

## রুট কজ (এক লাইনে)

`.githooks/pre-commit` ও `.githooks/post-commit`-এর **git-mode 100644** (non-executable) — কিন্তু pre-push-এর umbrella self-test-এর S8/S9 দুটোই `test -x` দাবি করে; fresh clone-এ git মোড মানে বলে hook নীরবে skip → self-test RED। **pre-push নিজে 100755** বলে শুধু sibling-রা ভেঙে পড়ে।

## কেন এই ত্রুটি লক্ষ্যের বাইরে রইল (সততা-নোট)

আমার এজেন্ট-রানটাইমের filesystem exec-bit-noise (সব ফাইল 755) `sh .githooks/pre-push --self-test`-কে মিথ্যা সবুজ দেখিয়েছিল (গত সাইকেলে 9/9 রেকর্ড করেছি); আর landed রিসিট-লেখক সম্ভবত একই-শ্রেণির রানটাইমে ছিলেন না — বা টাওয়ার-পাঠক ফাইলের মোড দেখেননি। মোড-সচেতন পরীক্ষাই সত্য দেখায়: **clone সত্য, runtime noise মিথ্যা।**

## প্রমাণ-চেইন (প্রথম-হাতে, মোড-সচেতন TDD)

1. **রিপো-মোড অনুকরণ** (`chmod 644` দুটি sibling-এ): `sh .githooks/pre-push --self-test` → `FAIL pre-commit-sibling-verified` + `FAIL post-commit-sibling-verified` → **"self-test: 2 scenario(s) FAILED"** (exit 1) — glm20-এর বর্ণনার হুবহু পুনঃসৃজন।
2. **Fresh clone** (`git clone` local repo): মোড `-rw-`/`-rw-`/`-rwx` → একই 2 FAIL — প্রোডাকশন-সত্য নিশ্চিত।
3. **Fix apply:** mode-only unified diff (কনটেন্ট অপরিবর্তিত) `git apply` → মোড `-rwx` দুটিতে → self-test **"9/9 scenarios PASS"** (exit 0)।
4. **নন-রিগ্রেশন:** diff শুধু 4 লাইনের mode-লাইন (2 ফাইল × old/new mode); কোনো কনটেন্ট-বাইট স্পর্শ নেই — hook-আচরণ, self-test স্ক্রিপ্ট, অন্য কোনো গার্ড অপরিবর্তিত।

## কেন এটাই রুট-ফিক্স (পুনরাবৃত্তি-নিবারণ)

- `git update-index --chmod=+x`-সমতুল্য মোড-পিন রিপো-তে স্থায়ী — যেকোনো fresh clone/CI runner/agent runtime-এ self-test এখন থেকে সত্য সবুজ।
- বিকল্প-প্রত্যাখ্যান: (১) S8/S9-এর `test -x` শিথিল করা — নিষেধ (এটাই #3520-এর fail-closed অদ্রব্য; git নীরবে non-executable hook skip করে — শিথিলতা মিথ্যা-সবুজ ফিরিয়ে আনবে); (২) CI-তে প্রতি-রান chmod — রানটাইম-প্লাস্টার, রিপো-সত্য অপরিবর্তিত থাকত; (৩) রিসিট-only — ফাইন্ডিং সত্য কিন্তু remedy ছাড়া প্রতি fresh clone-এ RED রয়ে যেত।

## ডেলিভারি-নোট (জমার সময়ের বাস্তব ফলাফল)

মোড-পরিবর্তন ব্রিজ-ইনগ্রেসে যাওয়ার **আজ কোনো পথ নেই — প্রথম-হাতে প্রমাণিত**:
(১) `unified_diff` + mode-only diff (সঠিক `diff` ফিল্ডে) → tower validator:
`diff failed to parse: unrecognized diff line 2: old mode 100644` — parser
হাঙ্ক-ব্যাকরণে সীমাবদ্ধ, mode-line চেনে না (fail-closed); (২) `full_file` বাহক
কনটেন্ট-ই লেখে, মোড-সংকেত নেই। অর্থাৎ **টাওয়ার-লেন স্ট্রাকচারাল শিক্ষা** (#3561-
শ্রেণির intake-শিক্ষার মতো): মোড-ধারী ফিক্সের জন্য unified_diff-এ `old mode/new
mode` লাইনের স্বীকৃতি যোগ করা দরকার — নইলে git-metadata-শ্রেণির প্রতিটি ভবিষ্যৎ
ত্রুটি (exec-bit, symlink, mode-drift) রিপোর্টযোগ্য হলেও অমীমাংসেয় থাকবে।

**এক-লাইন admin রেসিপি** (protected-লেন, পূর্ণ প্রমাণ-চেইন এই রিসিটেই):

```
git update-index --chmod=+x .githooks/pre-commit .githooks/post-commit
```

সাথে সংশ্লিষ্ট গার্ড-শিক্ষা (U6): মোড-সংবেদনশীল self-test-গুলোর সবুজ-সাক্ষ্য
runtime-filesystem থেকে না নিয়ে `git ls-files -s` (রিপো-মোড) থেকে নেওয়াই
সত্য-উৎস — আমার নিজের গত-সাইকেলের 9/9 মিথ্যা-সবুজ এখান থেকেই।
