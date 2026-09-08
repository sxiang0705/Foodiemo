"""One guarded test entry point. Unit tests never connect to any database."""
import argparse
import os
from pathlib import Path
import sys
from dotenv import load_dotenv
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--integration", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.integration:
        if not (ROOT / ".env.test").exists():
            sys.exit("Missing isolated .env.test")
        load_dotenv(ROOT / ".env.test", override=True, encoding="utf-8-sig")
        from app.core.config import Settings
        from app.core.safety import assert_test_target
        assert_test_target(Settings.from_env())
        os.environ["RUN_PG_TESTS"] = "1"
        sys.exit(pytest.main(["-q", "tests/test_integration.py"]))
    sys.exit(pytest.main(["-q", "tests/test_unit.py"]))
