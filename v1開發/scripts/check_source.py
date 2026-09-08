"""Review the actual Git candidate set without printing credential values."""
import re
import subprocess
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "v1開發"
result = subprocess.run(["git", "-c", "safe.directory=" + ROOT.as_posix(), "ls-files",
                         "--cached", "--others", "--exclude-standard", "-z"],
                        cwd=ROOT, capture_output=True, check=True)
paths = sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})
secrets = []
for env_file in [V1 / ".env", V1 / ".env.test"]:
    for key, value in dotenv_values(env_file, encoding="utf-8-sig").items():
        if value and ("PASSWORD" in key or "TOKEN" in key) and len(value) >= 8:
            secrets.append(value)
failures = []
for relative in paths:
    p = ROOT / relative
    if not p.is_file():
        continue
    forbidden_parts = {".venv", ".local", "backups", "uploads", "test-uploads", "test-results", "node_modules", "__pycache__"}
    if forbidden_parts.intersection(p.parts) or (p.name.startswith(".env") and p.name != ".env.example") or p.suffix in {".dump", ".backup", ".db", ".pem", ".key"}:
        failures.append(relative + ": forbidden file")
        continue
    # Scan both the staged blob and current working tree, not just filenames.
    staged = subprocess.run(["git", "-c", "safe.directory=" + ROOT.as_posix(), "show", ":" + relative],
                            cwd=ROOT, capture_output=True)
    content = p.read_text(encoding="utf-8-sig")
    if staged.returncode == 0:
        content += "\n" + staged.stdout.decode("utf-8-sig")
    if any(secret in content for secret in secrets):
        failures.append(relative + ": local credential detected")
    if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", content):
        failures.append(relative + ": private key detected")
    if p.name == "baseline.sql" and re.search(r"(?m)^(COPY |INSERT INTO )", content):
        failures.append(relative + ": baseline contains row data")
if failures:
    raise SystemExit("\n".join(failures))
print(f"PASS: {len(paths)} Git candidate files; local credentials and excluded artifacts absent.")
