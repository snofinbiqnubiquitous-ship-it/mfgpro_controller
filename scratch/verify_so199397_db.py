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
OUTPUT TO "/tmp/sod_data_98_final.txt".
PUT UNFORMATTED "=== SO_MSTR ===" SKIP.
FOR EACH so_mstr NO-LOCK WHERE so_nbr = "SO199398":
    EXPORT so_nbr so_cust so_ship so_ord_date so_req_date so_due_date so_po so_stat so_taxable so_tax_env.
END.
PUT UNFORMATTED "=== SOD_DET ===" SKIP.
FOR EACH sod_det NO-LOCK WHERE sod_nbr = "SO199398":
    EXPORT sod_nbr sod_line sod_part sod_qty_ord sod_um sod_price sod_site sod_status.
END.
OUTPUT CLOSE.
QUIT.
"""

stdin, stdout, stderr = ssh.exec_command("cat << 'EOF' > /tmp/query_sod97_final.p\n" + p_script + "\nEOF\n")
stdout.channel.recv_exit_status()

cmd = """
DLC=/usr/dlc101b
export DLC
PATH=$PATH:$DLC/bin
export PATH
PROSTARTUP=/usr/dlc101b/japanese.pf
export PROSTARTUP
$DLC/bin/_progres /livejpdb/livejpdb -ld livejpdb -ro -b -p /tmp/query_sod97_final.p > /dev/null 2>&1
cat /tmp/sod_data_98_final.txt 2>/dev/null
"""
stdin, stdout, stderr = ssh.exec_command(cmd)
raw = stdout.read()
text = raw.decode("cp932", errors="replace")
print("=== DB QUERY RESULTS FOR SO199397 ===")
print(text)

ssh.close()
