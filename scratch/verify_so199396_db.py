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

# sod_det (Sales Order Detail) を照会
p_script = """
OUTPUT TO "/tmp/sod_data.txt".
FOR EACH sod_det NO-LOCK WHERE sod_nbr = "SO199396":
    EXPORT sod_nbr sod_line sod_part sod_qty_ord sod_price sod_site.
END.
OUTPUT CLOSE.
QUIT.
"""

stdin, stdout, stderr = ssh.exec_command("cat << 'EOF' > /tmp/query_sod.p\n" + p_script + "\nEOF\n")
stdout.channel.recv_exit_status()

cmd = """
DLC=/usr/dlc101b
export DLC
PATH=$PATH:$DLC/bin
export PATH
PROSTARTUP=/usr/dlc101b/japanese.pf
export PROSTARTUP
$DLC/bin/_progres /livejpdb/livejpdb -ld livejpdb -ro -b -p /tmp/query_sod.p > /tmp/query.log 2>&1
cat /tmp/sod_data.txt 2>/dev/null
"""

stdin, stdout, stderr = ssh.exec_command(cmd)
raw = stdout.read()
text = raw.decode("cp932", errors="replace")
print("SOD_DET RECORDS FOR SO199396:")
print(text)

ssh.close()
