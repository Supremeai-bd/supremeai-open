#!/usr/bin/env bash
# cleanup_duplicate_health_scripts.sh
# =====================================
# এই স্ক্রিপ্টটা পুরনো, ডুপ্লিকেট/এতিম হেলথ-চেক স্ক্রিপ্ট দুটো সরিয়ে দেয়
# এবং নতুন ক্যানোনিকাল scripts/health/check_system_health.py বসায়।
#
# চালানোর আগে অবশ্যই একটা নতুন branch/commit এ থাকুন যাতে সহজে revert করা যায়:
#   git checkout -b chore/merge-duplicate-health-scripts
#
# ব্যবহার: bash cleanup_duplicate_health_scripts.sh  (প্রজেক্ট রুট থেকে চালান)

set -euo pipefail

echo "🔎 ধাপ ১: নতুন ক্যানোনিকাল স্ক্রিপ্ট বসানো হচ্ছে..."
mkdir -p scripts/health
cp check_system_health.py scripts/health/check_system_health.py
chmod +x scripts/health/check_system_health.py

echo "🗑️  ধাপ ২: পুরনো ডুপ্লিকেট/এতিম স্ক্রিপ্ট মুছে ফেলা হচ্ছে..."
git rm -f scripts/health/auto_health_check.py 2>/dev/null || rm -f scripts/health/auto_health_check.py
git rm -f scripts/health_check/auto_health_check.py 2>/dev/null || rm -f scripts/health_check/auto_health_check.py
rmdir scripts/health_check 2>/dev/null || true

echo "🧹 ধাপ ৩: .pre-commit-config.yaml থেকে পুরনো exclude রেফারেন্স সরানো হচ্ছে..."
if [ -f .pre-commit-config.yaml ]; then
  sed -i.bak 's#|scripts/health_check/auto_health_check\\.py##g; s#scripts/health_check/auto_health_check\\.py|##g; s#scripts/health_check/auto_health_check\\.py##g' .pre-commit-config.yaml
  rm -f .pre-commit-config.yaml.bak
  echo "   ⚠️  .pre-commit-config.yaml manually চেক করে নিন — regex সবসময় নিখুঁত না-ও হতে পারে।"
fi

echo "✅ ধাপ ৪: নতুন স্ক্রিপ্ট গিটে যোগ করা হচ্ছে..."
git add scripts/health/check_system_health.py .pre-commit-config.yaml 2>/dev/null || true

echo ""
echo "সম্পন্ন! এখন করণীয়:"
echo "  1. git status দেখে ভেরিফাই করুন"
echo "  2. python scripts/health/check_system_health.py --skip-db --skip-redis চালিয়ে টেস্ট করুন"
echo "  3. .github/workflows/maintenance_pipeline.yml এ 'poetry run python -m backend.tools.health_checker'"
echo "     লাইনটা চাইলে 'poetry run python scripts/health/check_system_health.py' দিয়ে replace করতে পারেন"
echo "     (backend.tools.health_checker.HealthChecker ক্লাসটা এখনো ব্যবহার হচ্ছে, তাই ওই ফাইলটা মুছবেন না)"
echo "  4. git commit -m 'chore: merge 3 duplicate health-check scripts into one canonical script'"
