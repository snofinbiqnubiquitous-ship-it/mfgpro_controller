import base64
import json
from pathlib import Path
import paramiko

repo_dir = Path(r"c:\Users\0138018\.antigravity\mfgpro_controller")
with open(repo_dir / "terminal_config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(cfg["host"], port=cfg.get("port", 22), username=cfg["user"], password=base64.b64decode(cfg["pass_b64"]).decode("utf-8"), timeout=12)

cmd = "sed -n '420,470p' /usr/dlc101b/protermcap"
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== PROTERMCAP VT100 (420-470) ===")
print(stdout.read().decode("utf-8", errors="replace"))

ssh.close()
