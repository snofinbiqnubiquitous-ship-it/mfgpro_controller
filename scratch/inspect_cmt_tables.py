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
OUTPUT TO "/tmp/inspect_cmt.txt".
FOR EACH _file WHERE _file-name MATCHES "*cmt*" NO-LOCK:
    PUT UNFORMATTED "Table: " _file-name SKIP.
    FOR EACH _field OF _file NO-LOCK:
        PUT UNFORMATTED "  Field: " _field-name " Type: " _data-type SKIP.
    END.
END.

FOR EACH _file WHERE _file-name = "so_mstr" NO-LOCK:
    PUT UNFORMATTED "so_mstr comment fields:" SKIP.
    FOR EACH _field OF _file WHERE _field-name MATCHES "*cmt*" OR _field-name MATCHES "*comm*" NO-LOCK:
        PUT UNFORMATTED "  Field: " _field-name " Type: " _data-type SKIP.
    END.
END.

OUTPUT CLOSE.
QUIT.
"""

stdin, stdout, stderr = ssh.exec_command("cat << 'EOF' > /tmp/inspect_cmt.p\n" + p_script + "\nEOF\n")
stdout.channel.recv_exit_status()

cmd = """
DLC=/usr/dlc101b
export DLC
PATH=$PATH:$DLC/bin
export PATH
PROSTARTUP=/usr/dlc101b/japanese.pf
export PROSTARTUP
$DLC/bin/_progres /livejpdb/livejpdb -ld livejpdb -ro -b -p /tmp/inspect_cmt.p > /dev/null 2>&1
cat /tmp/inspect_cmt.txt 2>/dev/null
"""
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode("cp932", errors="replace")
print("OUT:\n", out)

ssh.close()
