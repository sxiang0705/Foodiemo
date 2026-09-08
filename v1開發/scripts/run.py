import argparse
from pathlib import Path
import sys
from dotenv import load_dotenv
import uvicorn
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
parser = argparse.ArgumentParser()
parser.add_argument("--test", action="store_true")
args = parser.parse_args()
if args.test:
    if not (ROOT / ".env.test").exists():
        sys.exit("Missing .env.test")
    load_dotenv(ROOT / ".env.test", override=True, encoding="utf-8-sig")
    from app.core.config import Settings
    from app.core.safety import assert_test_target
    assert_test_target(Settings.from_env())
uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1",
            port=8001 if args.test else 8000, access_log=False)
