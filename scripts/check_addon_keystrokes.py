"""Compare QAD keystrokes of the pre-add-on workers (git ref) with the add-ons.

Usage: python -X utf8 scripts/check_addon_keystrokes.py [git-ref]  (default 3e9d94a)
"""
import ast, datetime, sys, types, importlib.util, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
REF = sys.argv[1] if len(sys.argv) > 1 else "3e9d94a"
sys.path.insert(0, str(ROOT))
from tests.qad_fakes import FakeClock, FakeShell, FakeClient, login_replies, prn_stream
from qad_report import ReportShell, KEY_CTRL_F

old_source = subprocess.run(['git', 'show', f'{REF}:自作モダンターミナル.pyw'], cwd=ROOT, capture_output=True, check=True).stdout.decode('utf-8')
tree = ast.parse(old_source)
module_funcs = {}
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        module_funcs[node.name] = node  # later definitions win, like at runtime
methods = {}
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == 'TerminalApp':
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods[item.name] = item

class Recorder:
    def __init__(self):
        self.clock = FakeClock()
        self.events = []
    def sleep(self, s):
        if s not in (0.05, 0.1):
            self.events.append(('sleep', round(s, 3)))
        self.clock.sleep(s)

class RecordingShell(FakeShell):
    def __init__(self, rec, replies):
        super().__init__(rec.clock, replies)
        self.rec = rec
    def send(self, data):
        self.rec.events.append(('send', data))
        super().send(data)

def old_run(method_names, replies_list, args):
    rec = Recorder()
    fake_time = types.SimpleNamespace(time=rec.clock, sleep=rec.sleep)
    shells = iter(replies_list)
    class SSH:
        def __init__(self):
            self.client = FakeClient(RecordingShell(rec, next(shells)))
        def set_missing_host_key_policy(self, p): pass
        def __getattr__(self, name): return getattr(self.client, name)
    ns = {'time': fake_time, 're': __import__('re'), 'datetime': datetime, 'codecs': __import__('codecs'), 'gzip': __import__('gzip'),
          'paramiko': types.SimpleNamespace(SSHClient=SSH, AutoAddPolicy=lambda: None),
          'send_to_gas_via_browser': lambda *a, **k: rec.events.append(('gas', len(a[0]) if isinstance(a[0], list) else a[0]['menu'])),
          'log_info': lambda *a, **k: None, 'log_error': lambda *a, **k: None,
          'INVENTORY_GAS_URL': 'i', 'COMPLAINT_GAS_URL': 'c', 'PARALLEL_GAS_URL': 'p'}
    for name in ('_clear_shell_buffer', '_wait_shell_text', 'decode_32prn_stream', 'clean_printer_data', 'convert_date_format', 'parse_report_to_rows'):
        exec(compile(ast.Module(body=[module_funcs[name]], type_ignores=[]), 'old', 'exec'), ns)
    for name in method_names:
        exec(compile(ast.Module(body=[methods[name]], type_ignores=[]), 'old', 'exec'), ns)
    app = types.SimpleNamespace(set_status=lambda *a, **k: None, after=lambda d, f: None,
                                _update_data_transmission_buttons_state=lambda: None)
    for name in method_names:
        setattr(app, name, types.MethodType(ns[name], app))
    getattr(app, method_names[0])(*args)
    return rec.events

def new_run(procedure, replies, *args):
    rec = Recorder()
    shell = RecordingShell(rec, replies)
    report = ReportShell('h', 22, 'u', 'p', client_factory=lambda: FakeClient(shell), clock=rec.clock, sleep=rec.sleep)
    procedure(report, lambda text: None, *args)
    report.receive_rows(300)
    return rec.events

spec = importlib.util.spec_from_file_location('dt', ROOT / 'addons' / 'data_transmission.py')
dt = importlib.util.module_from_spec(spec); spec.loader.exec_module(dt)

def replies(after='Selection:', screen=None, prompt=True):
    r = login_replies(after, prompt)
    if screen: r[screen[0]] = [(0.5, screen[1])]
    r[KEY_CTRL_F] = [(1.0, prn_stream())]
    return r

cases = {
    'inventory': (old_run(['_run_inventory_gas_transmission_worker'], [replies()], ('h', 22, 'u', 'p')),
                  new_run(dt.extract_inventory, replies())),
    'complaint': (old_run(['_run_complaint_gas_transmission_worker'], [replies('Roll Japan Production', ('99.3.21.4\r', 'Item Number'))],
                          ('h', 22, 'u', 'p', 'BW0100D', '04/01/26', '10/02/26', 'N1', None)),
                  new_run(dt.extract_complaint, replies('Roll Japan Production', ('99.3.21.4\r', 'Item Number')), 'BW0100D', '04/01/26', '10/02/26', 'N1')),
    'order_backlog': (old_run(['_parallel_extract_99_7_6_20'], [replies(screen=('99.7.6.20\r', 'Sales Order'))], ('h', 22, 'u', 'p')),
                      new_run(dt.extract_order_backlog, replies(screen=('99.7.6.20\r', 'Sales Order')))),
    'sales': (old_run(['_parallel_extract_99_7_5_11'], [replies(screen=('99.7.5.11\r', 'Invoice'))], ('h', 22, 'u', 'p')),
              new_run(lambda s, p: dt.extract_sales(s, p, datetime.date.today().replace(day=1).strftime('%m/%d/%y'), datetime.date.today().strftime('%m/%d/%y')),
                      replies(screen=('99.7.5.11\r', 'Invoice')))),
}
for name, (old, new) in cases.items():
    old_keys = [e for e in old if e[0] in ('send', 'sleep')]
    same = old_keys == new
    print(f'{name}: sends={sum(1 for e in new if e[0]=="send")} fixed_waits={sum(1 for e in new if e[0]=="sleep")} identical={same}')
    if not same:
        for i, (a, b) in enumerate(zip(old_keys, new)):
            if a != b:
                print('  first difference at', i, a, b); break
        print('  lengths', len(old_keys), len(new))

sys.exit(0 if all([e for e in o if e[0] in ('send', 'sleep')] == n for o, n in cases.values()) else 1)
