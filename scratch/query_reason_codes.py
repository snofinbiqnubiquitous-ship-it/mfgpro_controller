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

# 4GLスクリプトを作成
p_script = """
OUTPUT TO "/tmp/reason_codes.txt".
FOR EACH rsn_mstr NO-LOCK WHERE rsn_type = "SOLISTPR":
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
$DLC/bin/_progres -b /livejpdb/livejpdb -ld livejpdb -ro -p /tmp/query_rsn.p > /tmp/query.log 2>&1
cat /tmp/reason_codes.txt
"""

stdin, stdout, stderr = ssh.exec_command(cmd)
print("REASON CODES:\n", stdout.read().decode("cp932", errors="replace"))
print("LOG:\n", stderr.read().decode("cp932", errors="replace"))

# /tmp のファイルをクリーンアップ
ssh.exec_command("rm -f /tmp/query_rsn.p /tmp/reason_codes.txt /tmp/query.log")

ssh.close()
