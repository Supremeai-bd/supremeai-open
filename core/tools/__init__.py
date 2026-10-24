# বাংলা মন্তব্য: স্টার্টআপ ও ইম্পোর্ট টাইম কমাতে LazyModule ডিফাইন করা হলো।
# এটি `sys.modules` এ সাবমডিউলগুলোর ডামি প্রক্সি হিসেবে কাজ করবে এবং প্রথম অ্যাট্রিবিউট অ্যাক্সেসে
# আসল সাবমডিউল লোড করবে। ফলে `tools` ইম্পোর্ট করলেও হেভি ডিপেন্ডেন্সিগুলো ব্যাকগ্রাউন্ডে অলস (lazy) থাকবে।
import importlib
import sys
import types


class LazyModule(types.ModuleType):
    """লেজি মডিউল প্রক্সি — শুধুমাত্র প্রথম অ্যাট্রিবিউট অ্যাক্সেসে আসল মডিউল লোড করে।

    বাংলা মন্তব্য: `inspect.getmodule()` বা `hasattr(module, '__file__')`-এর মতো
    ইন্টার্নাল পাইথন অপারেশন যাতে অপ্রয়োজনীয় লেজি লোডিং ট্রিগার না করে,
    সেজন্য `__file__`, `__name__`, `__package__`, `__path__`, `__loader__`,
    `__spec__`, `__cached__` — এই অ্যাট্রিবিউটগুলোর জন্য সরাসরি ফলব্যাক মান
    রিটার্ন করা হয়, প্রকৃত ইম্পোর্ট না করেই।
    """

    # বাংলা মন্তব্য: যে অ্যাট্রিবিউটগুলো লেজি লোডিং ট্রিগার করবে না
    _NO_LOAD_ATTRS = frozenset(
        {
            "__file__",
            "__name__",
            "__package__",
            "__path__",
            "__loader__",
            "__spec__",
            "__cached__",
        }
    )

    def __init__(self, name: str, real_path: str):
        super().__init__(name)
        self._real_path = real_path
        self._module = None

    def _load(self):
        """প্রথম কলেই আসল মডিউল ইম্পোর্ট করে এবং নিজের __dict__-এ মিশিয়ে দেয়।"""
        if self._module is None:
            self._module = importlib.import_module(self._real_path)
            self.__dict__.update(self._module.__dict__)
        return self._module

    def __getattr__(self, item):
        # বাংলা মন্তব্য: inspect.getmodule()-এর মতো ইন্টার্নাল অপারেশন
        # লেজি লোডিং ট্রিগার করা থেকে বিরত রাখা
        if item in self._NO_LOAD_ATTRS:
            # __file__ চেক করলে None রিটার্ন করলে inspect.getmodule() সেটিকে
            # "লোড না হওয়া মডিউল" হিসেবে বিবেচনা করবে এবং ModuleNotFoundError
            # এড়িয়ে যাবে।
            if item == "__file__":
                return None
            if item == "__name__":
                return self.__name__
            if item == "__package__":
                return None
            if item == "__path__":
                return []
            if item == "__loader__":
                return None
            if item == "__spec__":
                return None
            if item == "__cached__":
                return None
        module = self._load()
        return getattr(module, item)

    def __dir__(self):
        module = self._load()
        return dir(module)


# isolated tests বা venv-এ sys.modules['tools'] KeyError এড়াতে সেলফ-ম্যাপিং
if "tools" not in sys.modules:
    sys.modules["tools"] = sys.modules[__name__]

# Ensure the directory containing this package (i.e., the parent of this file) is on sys.path
import os

_pkg_dir = os.path.dirname(__file__)
_parent_dir = os.path.dirname(_pkg_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

_SUBMODULE_MAP = {
    "mcp_cloud_deploy": "tools.mcp.mcp_cloud_deploy",
    "mcp_github_cicd": "tools.mcp.mcp_github_cicd",
    "mcp_supabase": "tools.mcp.mcp_supabase",
    "mcp_workspace": "tools.mcp.mcp_workspace",
    "bangla_voice": "tools.localization.bangla_voice",
    "model_trainer": "tools.learning.model_trainer",
    "pr_reviewer": "tools.code.pr_reviewer",
    "skill_recommender": "tools.learning.skill_recommender",
    "browser_agent": "tools.ai_agents.browser_agent",
    "style_learner": "tools.learning.style_learner",
    "auto_coverage_improver": "tools.devops.auto_coverage_improver",
    "image_to_code": "tools.code.image_to_code",
    "multilingual_tts": "tools.media.multilingual_tts",
}

# sys.modules এ প্রক্সি রেজিস্টার করা
for name, real_path in _SUBMODULE_MAP.items():
    lazy_mod = LazyModule(f"tools.{name}", real_path)
    sys.modules[f"tools.{name}"] = lazy_mod
    setattr(sys.modules[__name__], name, lazy_mod)

__all__ = list(_SUBMODULE_MAP.keys())
