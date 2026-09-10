"""Read-only live API-to-PostgreSQL cross-check. No fixtures or mutations."""
import json
from pathlib import Path
import sys
import httpx
from sqlalchemy import text
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.core.config import Settings
from app.core.database import build_engine

def main():
    engine=build_engine(Settings.from_env())
    with httpx.Client(base_url="http://127.0.0.1:8002",timeout=15) as client,engine.connect() as c:
        assert c.execute(text("SHOW transaction_read_only")).scalar()=="on"
        assert c.execute(text("SELECT version_num FROM public.alembic_version")).scalar()=="0001_baseline"
        response=client.get("/api/restaurants/recommendations?count=3")
        response.raise_for_status()
        data=response.json()
        assert data["source"]=="postgresql" and len(data["items"])==3
        for item in data["items"]:
            record=c.execute(text("SELECT title,address FROM public.restaurant_rows WHERE restaurant_id=:id"),
                             {"id":int(item["id"])}).one()
            assert (item["title"],item["address"])==tuple(record)
        again=client.get("/api/restaurants/recommendations",params={"count":3,"cursor":data["next_cursor"]}).json()
        assert again["items"][0]["id"]!=data["items"][0]["id"]
        result={"source":"project_db","readonly":True,"baseline":"0001_baseline",
                "matched_cards":len(data["items"]),"rotation":True,"algorithm_version":data["algorithm_version"]}
        (ROOT/"test-results").mkdir(exist_ok=True)
        (ROOT/"test-results/live-result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        print("PASS live API cards match PostgreSQL; next batch rotates; production baseline unchanged")
    engine.dispose()
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("Live smoke failed: "+type(exc).__name__,file=sys.stderr)
        sys.exit(1)

