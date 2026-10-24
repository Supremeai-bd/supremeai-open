import json
import os

from core.logging_config import logger

# বাংলা মন্তব্য: টেস্ট ও রিলায়েবিলিটি গেটের জন্য environment overrides fallback নির্ধারণ করা হলো
BASE_DIR = os.getenv("SUPREMEAI_BASE_DIR") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
DATA_DIR = os.getenv("SUPREMEAI_DATA_DIR") or os.path.join(BASE_DIR, "data")
MEMORY_FILE_PATH = os.getenv("SUPREMEAI_MEMORY_FILE_PATH") or os.path.join(
    DATA_DIR, "memory_vault.json"
)

# ফাইল না থাকলে তৈরি করে নিবে
# বাংলা: Render-এর মতো প্ল্যাটফর্মে /app read-only হতে পারে (persistent disk মাউন্ট না
# থাকলে) — আগে এখানে os.makedirs() unconditionally, কোনো try/except ছাড়া কল হতো, যেটা
# PermissionError দিয়ে ক্র্যাশ করত import-time-এই, আর ফলে এই মডিউল import করা প্রতিটা
# router (যেমন agent_workspace) পুরোপুরি load হতে ব্যর্থ হতো। এখন writable না হলে
# /tmp-এ fallback করা হয় (admin/god.py-তে যেভাবে করা হয়েছে, সেই একই প্যাটার্ন)।
try:
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
except PermissionError:
    logger.warning(
        f"Permission denied creating directory for {DATA_DIR}. Falling back to /tmp/data."
    )
    DATA_DIR = os.path.join("/tmp", "data")
    MEMORY_FILE_PATH = os.getenv("SUPREMEAI_MEMORY_FILE_PATH") or os.path.join(
        DATA_DIR, "memory_vault.json"
    )
    os.makedirs(DATA_DIR, exist_ok=True)

try:
    if not os.path.exists(MEMORY_FILE_PATH):
        with open(MEMORY_FILE_PATH, "w") as f:
            json.dump({}, f)
except PermissionError:
    logger.warning(f"Permission denied writing {MEMORY_FILE_PATH}. Falling back to /tmp/data.")
    DATA_DIR = os.path.join("/tmp", "data")
    os.makedirs(DATA_DIR, exist_ok=True)
    MEMORY_FILE_PATH = os.path.join(DATA_DIR, "memory_vault.json")
    with open(MEMORY_FILE_PATH, "w") as f:
        json.dump({}, f)


def get_from_memory(prompt: str, user_id: str | None = None):
    """ইউজারের প্রম্পটটি আগে সমাধান করা হয়েছে কি না, তা চেক করবে

    বাংলা মন্তব্য: user_id যোগ করা হয়েছে tenant-scoped memory জন্য (cache poisoning প্রতিরোধ)
    """
    with open(MEMORY_FILE_PATH) as f:
        memory = json.load(f)
        # বাংলা মন্তব্য: user_id থাকলে user-specific key ব্যবহার করা
        if user_id:
            key = f"{user_id}:{prompt}"
        else:
            key = prompt
        return memory.get(key, None)


def save_to_memory(prompt: str, solution_code: str, user_id: str | None = None):
    """নতুন সমাধান শিখলে সেটি জিরো-কস্ট মেমোরিতে সেভ করে রাখবে

    বাংলা মন্তব্য: user_id যোগ করা হয়েছে tenant-scoped memory জন্য (cache poisoning প্রতিরোধ)
    """
    with open(MEMORY_FILE_PATH) as f:
        memory = json.load(f)

    # বাংলা মন্তব্য: user_id থাকলে user-specific key ব্যবহার করা
    if user_id:
        key = f"{user_id}:{prompt}"
    else:
        key = prompt

    memory[key] = solution_code

    with open(MEMORY_FILE_PATH, "w") as f:
        json.dump(memory, f, indent=4)
    logger.info("🧠 [Auto-Didact] New skill learned and saved to memory vault!")
