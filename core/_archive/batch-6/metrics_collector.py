# DEPRECATED: backend.core.metrics_collector -> backend.monitoring.metrics_collector
# নোট: backend architecture refactor plan অনুযায়ী সরানো হয়েছে।
# ভবিষ্যতে সব importer নতুন path-এ সরিয়ে এই shim মুছে ফেলতে হবে।
import importlib
import warnings

_DEPRECATED_TARGET = "monitoring.metrics_collector"
_warned = False


def __getattr__(name):
    global _warned
    if not _warned:
        warnings.warn(
            "backend.core.metrics_collector is deprecated; import from monitoring.metrics_collector",
            DeprecationWarning,
            stacklevel=2,
        )
        _warned = True
    mod = importlib.import_module(_DEPRECATED_TARGET)
    return getattr(mod, name)


def __dir__():
    return list(importlib.import_module(_DEPRECATED_TARGET).__dict__.keys())
