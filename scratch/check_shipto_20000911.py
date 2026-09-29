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
OUTPUT TO "/tmp/check_shipto.txt".
FOR EACH cm_mstr NO-LOCK WHERE cm_addr = "20000911":
    EXPORT cm_addr cm_sort cm_type cm_active.
END.
FOR EACH ad_mstr NO-LOCK WHERE ad_addr = "20000911":
    EXPORT ad_addr ad_name ad_line1.
END.
OUTPUT CLOSE.
QUIT.
"""

stdin, stdout, stderr = ssh.exec_command("cat << 'EOF' > /tmp/query_shipto.p\n" + p_script + "\nEOF\n")
stdout.channel.recv_exit_status()

cmd = """
DLC=/usr/dlc101b
export DLC
PATH=$PATH:$DLC/bin
export PATH
PROSTARTUP=/usr/dlc101b/japanese.pf
export PROSTARTUP
$DLC/bin/_progres /livejpdb/livejpdb -ld livejpdb -ro -b -p /tmp/query_shipto.p > /tmp/query.log 2>&1
cat /tmp/check_shipto.txt 2>/dev/null
rm -f /tmp/query_shipto.p /tmp/check_shipto.txt /tmp/query.log
"""

stdin, stdout, stderr = ssh.exec_command(cmd)
raw = stdout.read()
text = raw.decode("cp932", errors="replace")
print("CHECK SHIP_TO 20000911:")
print(text)

ssh.close()
