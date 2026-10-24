# /conftest.py (repo root)
#
# বাংলা মন্তব্য: backend/-এর ভেতরের মডিউলগুলো (middleware, core, api ইত্যাদি) সবসময়
# "core.x", "middleware.x" স্টাইলে import করে — অর্থাৎ ধরে নেয় backend/ ফোল্ডারটাই সরাসরি
# sys.path-এ আছে। backend/tests/ এর নিজস্ব conftest.py সেটা করে দেয়, কিন্তু repo-root
# tests/ থেকে টেস্ট রান হলে (যেমন CI যখন backend/ থেকে "../tests" collect করে) backend/
# sys.path-এ থাকে না, ফলে "from core.config import settings"-জাতীয় লাইন
# "ModuleNotFoundError: No module named 'core...'; 'core' is not a package" দিয়ে ভাঙে।
#
# এই ফাইলটা pytest-এর conftest discovery-তে repo-root tests/-এর ancestor হিসেবে সবসময়
# লোড হয় (rootdir যেখানেই হোক), তাই এখানে backend/ কে path-এ যোগ করে দিলেই দুই টেস্ট-স্যুট
# একসাথে, নিরাপদে চলতে পারে — backend/-এর ভেতরের কোনো import-convention না পাল্টিয়েই।
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT in sys.path:
    sys.path.remove(_REPO_ROOT)
sys.path.insert(0, _REPO_ROOT)

_BACKEND_DIR = os.path.join(_REPO_ROOT, "backend")
if os.path.isdir(_BACKEND_DIR):
    if _BACKEND_DIR in sys.path:
        sys.path.remove(_BACKEND_DIR)
    sys.path.insert(1, _BACKEND_DIR)


