import base64
import json
from pathlib import Path
import paramiko

repo_dir = Path(r"c:\Users\0138018\.antigravity\mfgpro_controller")
with open(repo_dir / "terminal_config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

host = cfg["host"]
port = cfg.get("port", 22)
user = cfg["user"]
password = base64.b64decode(cfg["pass_b64"]).decode("utf-8")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, port=port, username=user, password=password, timeout=12)

import sys
sys.stdout.reconfigure(encoding='utf-8')
cmd = "grep '{' /mfgpro/eB2.1/xrc/sosomt.p"
stdin, stdout, stderr = ssh.exec_command(cmd)
res = stdout.read().decode("utf-8", errors="replace")
print("INCLUDES:\n", res[:2000])

ssh.close()
