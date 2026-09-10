"""Run the original frontend and same-origin PostgreSQL API."""
import argparse
from pathlib import Path
import sys
from dotenv import load_dotenv
import uvicorn
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--test",action="store_true")
    parser.add_argument("--port",type=int)
    args=parser.parse_args()
    if args.test:
        if not (ROOT/".env.test").exists(): sys.exit("Missing isolated .env.test")
        load_dotenv(ROOT/".env.test",override=True,encoding="utf-8-sig")
        from app.core.config import Settings
        from app.core.safety import assert_test_target
        assert_test_target(Settings.from_env())
    uvicorn.run("app.main:create_app",factory=True,host="127.0.0.1",
                port=args.port or (8003 if args.test else 8002),access_log=False)

