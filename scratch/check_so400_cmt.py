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
OUTPUT TO "/tmp/test_cmt_out.txt".
FOR EACH so_mstr NO-LOCK WHERE so_nbr = "SO199400":
    PUT UNFORMATTED "SO: " so_nbr " cust: " so_cust " cmtindx: " so_cmtindx SKIP.
    IF so_cmtindx > 0 THEN DO:
        FOR EACH cmt_det NO-LOCK WHERE cmt_indx = so_cmtindx:
            PUT UNFORMATTED "  seq: " cmt_seq " lang: " cmt_lang " type: " cmt_type " cmmt: " cmt_cmmt SKIP.
        END.
    END.
END.
OUTPUT CLOSE.
QUIT.
"""

stdin, stdout, stderr = ssh.exec_command("cat << 'EOF' > /tmp/test_cmt.p\n" + p_script + "\nEOF\n")
stdout.channel.recv_exit_status()

cmd = """
DLC=/usr/dlc101b
export DLC
PATH=$PATH:$DLC/bin
export PATH
PROSTARTUP=/usr/dlc101b/japanese.pf
export PROSTARTUP
rm -f /tmp/order_test5_db.txt
$DLC/bin/_progres /livejpdb/livejpdb -ld livejpdb -ro -b -p /tmp/query_test5.p
echo "QUERY_TEST5 EXIT: $?"
cat /tmp/order_test5_db.txt 2>/dev/null
"""
stdin, stdout, stderr = ssh.exec_command(cmd)
res = stdout.read().decode("cp932", errors="replace")
err = stderr.read().decode("cp932", errors="replace")
print("RESULT:\n", res)
print("STDERR:\n", err)

ssh.close()
