# DEPRECATED: backend.services.intelligent_cache -> backend.core.intelligent_cache
# নোট: services/intelligent_cache.py ছিল core/intelligent_cache.py-এর একটা
# পুরনো/স্টেল কপি (94% ফাইল-লেভেল ডুপ্লিকেট, duplicate_detector.py-তে ধরা
# পড়েছে) যেটাতে core সংস্করণের MEMLEAK-002 বাউন্ডেড-LRU ফিক্স, config-চালিত
# TTL, ও predictive cache engine integration ছিল না। একমাত্র importer
# (services/auto_healer.py) এখন সরাসরি canonical core মডিউল ব্যবহার করছে;
# অন্য কোনো legacy importer-এর জন্য এই shim রাখা হলো।
import importlib
import warnings

_DEPRECATED_TARGET = "core.intelligent_cache"
_warned = False


def __getattr__(name):
    global _warned
    if not _warned:
        warnings.warn(
            "backend.services.intelligent_cache is deprecated; import from core.intelligent_cache",
            DeprecationWarning,
            stacklevel=2,
        )
        _warned = True
    mod = importlib.import_module(_DEPRECATED_TARGET)
    return getattr(mod, name)


def __dir__():
    return list(importlib.import_module(_DEPRECATED_TARGET).__dict__.keys())
