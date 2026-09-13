"""Run the original frontend and same-origin PostgreSQL API."""
import argparse
import ipaddress
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
    parser.add_argument("--lan-ip",help="Bind an explicit private LAN IPv4 address for phone testing")
    args=parser.parse_args()
    host="127.0.0.1"
    if args.lan_ip:
        address=ipaddress.ip_address(args.lan_ip)
        allowed=any(address in ipaddress.ip_network(network) for network in ["10.0.0.0/8","172.16.0.0/12","192.168.0.0/16"])
        if args.test or address.version!=4 or not allowed:
            parser.error("LAN preview requires a private IPv4 address and cannot expose the test server")
        host=str(address)
    if args.test:
        if not (ROOT/".env.test").exists(): sys.exit("Missing isolated .env.test")
        load_dotenv(ROOT/".env.test",override=True,encoding="utf-8-sig")
        from app.core.config import Settings
        from app.core.safety import assert_test_target
        assert_test_target(Settings.from_env())
    uvicorn.run("app.main:create_app",factory=True,host=host,
                port=args.port or (8003 if args.test else 8002),access_log=False)

