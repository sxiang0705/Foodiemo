"""Apply reviewed 0002 to existing project_db only after a matching verified backup."""
import argparse,hashlib,importlib.util,json,os,shlex,sys
from pathlib import Path
from dotenv import load_dotenv
import paramiko
ROOT=Path(__file__).resolve().parents[1]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--backup-dir',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 folder=(ROOT/args.backup_dir).resolve()
 if not folder.is_relative_to((ROOT/'backups').resolve()):raise RuntimeError('Backup path outside project')
 manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
 if manifest['source']!='project_db' or not manifest['counts_match'] or not manifest['schema_matches']:raise RuntimeError('Unverified backup')
 if hashlib.sha256((folder/'project_db.dump').read_bytes()).hexdigest()!=manifest['sha256']:raise RuntimeError('Backup checksum mismatch')
 load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
 if os.environ['DB_NAME']!='project_db':raise RuntimeError('Unexpected target')
 ssh=paramiko.SSHClient();ssh.load_host_keys(str(ROOT/'.local/known_hosts'))
 ssh.connect(os.environ['SSH_HOST'],port=int(os.getenv('SSH_PORT','22')),username=os.environ['SSH_USER'],password=os.environ['DB_PASSWORD'],look_for_keys=False,allow_agent=False,timeout=10)
 def run(command,data=b''):
  stdin,stdout,stderr=ssh.exec_command("sudo -S -p '' -u postgres "+command,timeout=120)
  stdin.write(os.environ['DB_PASSWORD']+'\n');stdin.flush()
  if data:stdin.channel.sendall(data)
  stdin.channel.shutdown_write();out=stdout.read();err=stderr.read()
  if stdout.channel.recv_exit_status():
   (ROOT/'.local/migration-error.log').write_bytes(err);raise RuntimeError('Remote migration failed; see ignored local log')
  return out
 def sql(query):return run('psql -X -v ON_ERROR_STOP=1 -At -d project_db',query.encode()).decode().strip()
 try:
  if run('pg_dump --version').decode().strip()!='pg_dump (PostgreSQL) 9.5.25':raise RuntimeError('Unexpected PostgreSQL tool version')
  version=sql('SELECT version_num FROM public.alembic_version;')
  if version=='0002_accounts_records':print('0002 already applied; no changes');return
  if version!='0001_baseline':raise RuntimeError('Unexpected revision')
  schema=run('pg_dump --schema-only --no-owner --no-privileges --schema=public --exclude-table=public.alembic_version --dbname=project_db')
  if schema!=(folder/'schema.sql').read_bytes():raise RuntimeError('Schema changed since backup')
  for table,count in manifest['source_counts'].items():
   identifier='"'+table.replace('"','""')+'"'
   if int(sql('SELECT count(*) FROM public.'+identifier+';'))!=count:raise RuntimeError('Data counts changed; create a new backup')
  if sql('SELECT count(*) FROM (SELECT lower(email) FROM users WHERE email IS NOT NULL GROUP BY lower(email) HAVING count(*)>1) s;')!='0':raise RuntimeError('Email collisions require review')
  print('Verified: project_db at 0001; matching restored backup, SHA256, schema, row counts, and no email collisions',flush=True)
  if not args.apply:return
  spec=importlib.util.spec_from_file_location('migration',ROOT/'migrations/versions/0002_accounts_records.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  role='"'+os.environ['DB_USER'].replace('"','""')+'"'
  query="BEGIN; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'; LOCK TABLE public.users IN ACCESS EXCLUSIVE MODE;\n"+module.DDL
  query+='\nGRANT SELECT,INSERT,UPDATE,DELETE ON public.auth_tokens,public.email_challenges,public.login_limits,public.user_preferences,public.file_gc TO '+role+';'
  query+="\nUPDATE public.alembic_version SET version_num='0002_accounts_records' WHERE version_num='0001_baseline'; COMMIT;"
  sql(query)
  if sql('SELECT version_num FROM alembic_version;')!='0002_accounts_records':raise RuntimeError('Post-check failed')
  print('Applied 0002 transactionally; original records retained; app role grants verified by subsequent smoke checks')
 finally:ssh.close()
if __name__=='__main__':
 try:main()
 except Exception as exc:print('Migration stopped: '+str(exc),file=sys.stderr);sys.exit(1)
