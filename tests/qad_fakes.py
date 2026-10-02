"""No-network helpers: a virtual clock and a scripted QAD shell."""
import codecs
import gzip

REPORT_TEXT = "\n".join([
    "xxrpt.p           Test Report                 Date: 10/02/26",
    "Item Number      Qty  Due Date",
    "---------------- ---- --------",
    "BW0100D          10   10/03/26",
    "BW0116Q3-2       5    10/04/26",
    "",
    "End of Report",
])
REPORT_ROWS = [["Item Number", "Qty", "Due Date"], ["BW0100D", "10", "2026/10/03"],
               ["BW0116Q3-2", "5", "2026/10/04"]]


def prn_stream(text=REPORT_TEXT, terminator=b"end\r\n"):
    encoded = codecs.encode(gzip.compress(text.encode("cp932")), "uu")
    body = encoded.split(b"\n", 1)[1].rsplit(b"end\n", 1)[0]
    return b"begin 0 32PRINTER\r\n" + body.replace(b"\n", b"\r\n") + terminator


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeShell:
    """Delivers scheduled output; replies are triggered by exact sent strings."""

    def __init__(self, clock, replies=None, chunk_size=None):
        self.clock = clock
        self.replies = dict(replies or {})
        self.chunk_size = chunk_size
        self.pending = []
        self.sent = []

    def schedule(self, delay, data):
        if isinstance(data, str):
            data = data.encode("cp932")
        step = self.chunk_size or len(data) or 1
        for offset in range(0, len(data), step):
            self.pending.append((self.clock.now + delay, data[offset:offset + step]))
        self.pending.sort(key=lambda item: item[0])

    def recv_ready(self):
        return bool(self.pending) and self.pending[0][0] <= self.clock.now

    def recv(self, size):
        due, data = self.pending.pop(0)
        if len(data) > size:
            self.pending.insert(0, (due, data[size:]))
            data = data[:size]
        return data

    def send(self, data):
        self.sent.append(data)
        for delay, output in self.replies.get(data, ()):
            self.schedule(delay, output)

    def settimeout(self, value):
        pass


class FakeClient:
    def __init__(self, shell, fail_connect=None):
        self.shell = shell
        self.fail_connect = fail_connect
        self.closed = False
        self.shell_size = None

    def connect(self, *args, **kwargs):
        if self.fail_connect:
            raise self.fail_connect

    def get_transport(self):
        return None

    def invoke_shell(self, term, width, height):
        self.shell_size = (width, height)
        return self.shell

    def close(self):
        self.closed = True


def login_replies(after_select="Selection:", prompt=True):
    replies = {"2\r": [(0.2, f"Roll Japan Production\r\n{after_select}")]}
    if prompt:
        replies["1\r"] = [(0.3, "Pausing... Press space bar to continue")]
        replies[" "] = [(0.3, "mfmenu Main Menu\r\nPlease select a function:")]
    else:
        replies["1\r"] = [(0.3, "mfmenu Main Menu\r\nPlease select a function:")]
    return replies
