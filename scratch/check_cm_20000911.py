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
OUTPUT TO "/tmp/check_cm.txt".
FIND FIRST cm_mstr NO-LOCK WHERE cm_addr = "20000911" NO-ERROR.
IF AVAILABLE cm_mstr THEN
    PUT UNFORMATTED cm_addr " active=" cm_active " sort=" cm_sort SKIP.
ELSE
    PUT UNFORMATTED "cm_mstr NOT FOUND" SKIP.
OUTPUT CLOSE.
QUIT.
"""

stdin, stdout, stderr = ssh.exec_command("cat << 'EOF' > /tmp/query_cm.p\n" + p_script + "\nEOF\n")
stdout.channel.recv_exit_status()

cmd = """
DLC=/usr/dlc101b
export DLC
PATH=$PATH:$DLC/bin
export PATH
PROSTARTUP=/usr/dlc101b/japanese.pf
export PROSTARTUP
$DLC/bin/_progres /livejpdb/livejpdb -ld livejpdb -ro -b -p /tmp/query_cm.p > /tmp/query.log 2>&1
cat /tmp/check_cm.txt 2>/dev/null
rm -f /tmp/query_cm.p /tmp/check_cm.txt /tmp/query.log
"""

stdin, stdout, stderr = ssh.exec_command(cmd)
raw = stdout.read()
text = raw.decode("cp932", errors="replace")
print("CM_MSTR STATUS:")
print(text)

ssh.close()
