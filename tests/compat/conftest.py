import os
import sys

# Prevent argparse from parsing pytest's own argv, which would cause
# bazarr/app/get_args.py to exit with "unrecognized arguments".
os.environ["NO_CLI"] = "true"
os.environ.setdefault("SZ_USER_AGENT", "test")
os.environ.setdefault("BAZARR_VERSION", "test")

# Add bazarr source trees to sys.path so that `from bazarr.app.config import ...`
# resolves correctly, matching what tests/bazarr/conftest.py does.
_repo = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_repo, "libs"))
sys.path.insert(0, os.path.join(_repo, "bazarr"))
sys.path.insert(0, os.path.join(_repo, "custom_libs"))
