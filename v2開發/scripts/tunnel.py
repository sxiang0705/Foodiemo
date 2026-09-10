"""Loopback-only SSH tunnel. Secrets stay in ignored .env or the password prompt."""
import argparse
import getpass
import os
from pathlib import Path
import select
import socketserver
import sys
import paramiko
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--use-db-password-for-ssh",action="store_true")
    args=parser.parse_args()
    load_dotenv(ROOT/".env",encoding="utf-8-sig")
    if os.environ.get("DB_HOST") != "127.0.0.1":
        raise RuntimeError("Tunnel requires DB_HOST=127.0.0.1")
    password=(os.environ["DB_PASSWORD"] if args.use_db_password_for_ssh else
              os.getenv("SSH_PASSWORD") or getpass.getpass("SSH password: "))
    ssh=paramiko.SSHClient()
    ssh.load_host_keys(str(ROOT/".local/known_hosts"))
    ssh.connect(os.environ["SSH_HOST"],port=int(os.getenv("SSH_PORT","22")),
                username=os.environ["SSH_USER"],password=password,
                look_for_keys=False,allow_agent=False,timeout=10,banner_timeout=10,auth_timeout=10)
    transport=ssh.get_transport()
    transport.set_keepalive(15)
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            channel=None
            try:
                channel=transport.open_channel("direct-tcpip",("127.0.0.1",5432),
                                               self.request.getpeername(),timeout=5)
                if channel is None: return
                while transport.is_active():
                    readable,_,_=select.select([self.request,channel],[],[],15)
                    for source in readable:
                        data=source.recv(65536)
                        if not data:return
                        (channel if source is self.request else self.request).sendall(data)
            except (OSError,EOFError,paramiko.SSHException):
                pass
            finally:
                if channel:channel.close()
    class Forwarder(socketserver.ThreadingTCPServer):
        daemon_threads=True
        allow_reuse_address=True
    try:
        with Forwarder(("127.0.0.1",int(os.environ["DB_PORT"])),Handler) as server:
            print("v2 SSH tunnel ready on loopback",flush=True)
            server.serve_forever(poll_interval=0.5)
    finally:
        ssh.close()

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("Tunnel failed: "+type(exc).__name__,file=sys.stderr)
        sys.exit(1)

