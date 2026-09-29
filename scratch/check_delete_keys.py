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

# Check user profile and login scripts for stty or TERM
cmd = "cat .profile .bash_profile .bashrc 2>/dev/null"
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== PROFILE ===")
print(stdout.read().decode("utf-8", errors="replace"))

# Check protermcap for vt100/vt220 delete-character definitions
cmd2 = "grep -n -C 5 -i 'DELETE-CHAR' /usr/dlc101b/protermcap"
stdin, stdout, stderr = ssh.exec_command(cmd2)
print("=== PROTERMCAP DELETE-CHAR ===")
print(stdout.read().decode("utf-8", errors="replace"))

# Check protermcap for vt100 block
cmd3 = "sed -n '360,420p' /usr/dlc101b/protermcap"
stdin, stdout, stderr = ssh.exec_command(cmd3)
print("=== PROTERMCAP VT100 BLOCK ===")
print(stdout.read().decode("utf-8", errors="replace"))

ssh.close()
