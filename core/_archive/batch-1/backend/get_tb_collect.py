import importlib
import sys
import traceback

sys.path.insert(0, "..")  # add f:\supremeai to sys.path
sys.path.insert(0, ".")  # add f:\supremeai\backend to sys.path

try:
    importlib.import_module("tests.api.test_api_config_routes")
    print("SUCCESS")
except Exception:
    with open("traceback_collect.txt", "w") as f:
        traceback.print_exc(file=f)
    print("FAILED")
