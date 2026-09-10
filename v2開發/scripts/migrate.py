"""Test migration runner; existing production baseline is verified and stamped separately."""
import argparse
from pathlib import Path
import sys
from dotenv import load_dotenv
from alembic import command
from alembic.config import Config
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings
from app.core.safety import assert_test_target

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["upgrade", "current"])
    parser.add_argument("--env-file", default=".env.test")
    args = parser.parse_args()
    load_dotenv(ROOT / args.env_file, override=True, encoding="utf-8-sig")
    assert_test_target(Settings.from_env())
    config = Config(str(ROOT / "alembic.ini"))
    if args.action == "upgrade":
        command.upgrade(config, "head")
    else:
        command.current(config)
