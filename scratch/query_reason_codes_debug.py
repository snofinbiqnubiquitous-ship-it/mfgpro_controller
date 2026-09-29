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

p_script = """
OUTPUT TO "/tmp/reason_codes.txt".
FOR EACH rsn_mstr NO-LOCK:
    PUT UNFORMATTED rsn_code " | " rsn_type " | " rsn_desc SKIP.
END.
OUTPUT CLOSE.
QUIT.
"""

stdin, stdout, stderr = ssh.exec_command("cat << 'EOF' > /tmp/query_rsn.p\n" + p_script + "\nEOF\n")
stdout.channel.recv_exit_status()

cmd = """
DLC=/usr/dlc101b
export DLC
PATH=$PATH:$DLC/bin
export PATH
PROSTARTUP=/usr/dlc101b/japanese.pf
export PROSTARTUP
$DLC/bin/_progres /livejpdb/livejpdb -ld livejpdb -ro -b -p /tmp/query_rsn.p > /tmp/query.log 2>&1
cat /tmp/query.log
cat /tmp/reason_codes.txt 2>/dev/null
"""

stdin, stdout, stderr = ssh.exec_command(cmd)
print("OUT:\n", stdout.read().decode("cp932", errors="replace"))

ssh.close()
