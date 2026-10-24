#!/bin/bash
# বাংলা কমেন্ট: সুপ্রিম-এআই এর জিরো-কস্ট ডকার ও মেমোরি ক্যাশ প্রুনিং স্ক্রিপ্ট।
# এটি সার্ভারলেস এনভায়রনমেন্টে ক্যাশ ডিলিট করে ক্লাউড লিমিট মেইনটেইন করে।

echo "=========================================================="
echo "🚀 SupremeAI Zero-Cost Memory & Docker Cache Optimizer"
echo "=========================================================="

# ১. হেলথ চেক ভেরিফিকেশন (ক্লাউড ডলফিন অ্যাটাক ঝুঁকি প্রিভেনশন)
HEALTH_ENDPOINT="${BACKEND_URL:-http://localhost:8000}/health"
echo "🔍 Checking API Health at $HEALTH_ENDPOINT..."

HTTP_STATUS=$(curl -o /dev/null -s -w "%{http_code}\n" $HEALTH_ENDPOINT)

if [ "$HTTP_STATUS" -ne 200 ] && [ "$HTTP_STATUS" -ne 404 ]; then
    echo "🔥 CRITICAL: API is not healthy or unreachable (Status: $HTTP_STATUS). Aborting prune to prevent state loss."
    exit 1
fi
echo "✅ API Health Check passed. Proceeding with cache optimization."

# ২. ডকার ক্যাশ প্রুনিং
echo "🐳 Cleaning Docker resources..."
# --volumes বাদ দেওয়া হয়েছে ডেটা লস প্রিভেন্ট করতে, শুধু আনইউজড ইমেজ ও কন্টেইনার ডিলিট হবে
docker system prune -af
echo "✅ Docker cleanup completed."

# ৩. পাইথন ক্যাশ ক্লিনিং (লোকাল মেমোরি ফ্রি)
echo "🧹 Purging __pycache__ and .pytest_cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null
echo "✅ Local python cache cleared."

echo "=========================================================="
echo "🎉 Zero-Cost Optimization Pipeline Completed!"
echo "=========================================================="
