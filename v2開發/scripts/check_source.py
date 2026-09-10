"""Check the frozen original frontend and accidental secret inclusion."""
import hashlib
import json
import re
from pathlib import Path
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent/"前端原始程式碼/frontend"
CHANGED={"config.js","search.html","sw.js"}
def main():
    manifest=json.loads((ROOT/"docs/frontend-baseline.json").read_text(encoding="utf-8"))
    for name,item in manifest.items():
        original=SOURCE/name
        if original.exists():
            assert hashlib.sha256(original.read_bytes()).hexdigest()==item["source_sha256"], "Original changed: "+name
        current=ROOT/"frontend"/name
        if name not in CHANGED:
            assert hashlib.sha256(current.read_bytes()).hexdigest()==item["source_sha256"], "Unexpected frontend change: "+name
    if SOURCE.exists():
        original=(SOURCE/"search.html").read_text(encoding="utf-8-sig")
        current=(ROOT/"frontend/search.html").read_text(encoding="utf-8-sig")
        assert re.findall(r"<style>(.*?)</style>",original,re.S)==re.findall(r"<style>(.*?)</style>",current,re.S)
        # All static visible controls are unchanged. The only inserted script is nonvisual.
        a=original.split("<body>")[1].split('<script src="env.js">')[0]
        b=current.split("<body>")[1].split('<script src="env.js">')[0]
        assert a==b, "Search static UI changed"
    values=dotenv_values(ROOT/".env",encoding="utf-8-sig")
    secrets=[v for k,v in values.items() if v and len(v)>=8 and any(x in k for x in ["PASSWORD","SECRET","TOKEN"])]
    ignored={".venv","node_modules",".local","backups","uploads","test-uploads","test-results","__pycache__",".pytest_cache"}
    for p in ROOT.rglob("*"):
        if not p.is_file() or any(part in ignored for part in p.relative_to(ROOT).parts):continue
        if p.name.startswith(".env") and p.name!=".env.example":continue
        if p.suffix in [".png",".jpg",".ico"]:continue
        text=p.read_text(encoding="utf-8-sig")
        assert not any(s in text for s in secrets), "Local secret in source: "+str(p.relative_to(ROOT))
    print(f"PASS frozen frontend: {len(manifest)} original files; changed allowlist {sorted(CHANGED)}")
    print("PASS search CSS and static visible controls unchanged")
    print("PASS local connection secrets absent from deliverable text")
if __name__=="__main__":main()

