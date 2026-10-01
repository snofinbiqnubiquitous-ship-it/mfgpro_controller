"""仮想時刻と実際のCP932/VT100デコーダを使う、ネットワークなしの応答再現。"""

from collections import deque
from dataclasses import dataclass
import heapq
import queue

from terminal_core import TerminalSession


@dataclass
class ExpectedSend:
    data: str
    response: str | None = None
    delay: float = 0.0
    # 応答の後にさらに遅れて描画される画面（連続する警告や後から出るポップアップ）: (遅延秒, 画面)
    followup: tuple | None = None


class StrictReplay:
    def __init__(self, initial="", expected=()):
        self.now = 0.0
        self.terminal = TerminalSession("unused", 22, "unused", "unused", queue.Queue())
        self.stop_event = self.terminal.stop_event
        self.expected = deque(expected)
        self.events = []
        self.sequence = 0
        self.sent = []
        self.ready_at = 0.0
        self.terminal.feed(self.screen_bytes(initial))

    @staticmethod
    def screen_bytes(text):
        return ("\x1b[2J\x1b[H" + text.replace("\n", "\r\n")).encode("cp932")

    def schedule(self, delay, data):
        # Noneは切断イベント。任意の位置で分割した受信バイトも予約可能。
        self.sequence += 1
        heapq.heappush(self.events, (self.now + delay, self.sequence, data))

    def sleep(self, duration):
        self.now += duration
        while self.events and self.events[0][0] <= self.now:
            _, _, data = heapq.heappop(self.events)
            if data is None:
                self.stop_event.set()
            else:
                self.terminal.feed(data)

    def get_screen_text(self):
        return self.terminal.get_screen_text()

    def automation_snapshot(self):
        return self.terminal.automation_snapshot()

    @property
    def output_generation(self):
        # 本番のTerminalSessionと同じく、受信を画面へ反映した回数を返す
        return self.terminal.output_generation

    def send(self, data):
        if self.stop_event.is_set():
            raise AssertionError("切断後に送信した")
        if self.now < self.ready_at:
            raise AssertionError(f"応答前の先走り送信: {data!r}")
        if not self.expected:
            raise AssertionError(f"予定外の追加送信: {data!r}")
        expected = self.expected[0]
        if data != expected.data:
            raise AssertionError(f"送信不一致: expected={expected.data!r}, actual={data!r}")
        self.expected.popleft()
        self.sent.append((self.now, data))
        if expected.response is not None:
            self.ready_at = self.now + expected.delay
            self.schedule(expected.delay, self.screen_bytes(expected.response))
            if expected.followup is not None:
                later, screen = expected.followup
                self.ready_at = self.now + later
                self.schedule(later, self.screen_bytes(screen))
            self.sleep(0)

    def assert_finished(self):
        if self.expected:
            raise AssertionError(f"必要な送信が未実施: {self.expected[0].data!r}")


def step6_replay(early_warning=False, no_warning=False, delay=0.0, delayed=None, late_reason_code=False):
    """単一明細の合成シナリオ。実機ログをそのまま再現したものではない。"""
    f1, f4 = "\x1bOP", "\x1bOS"
    line = "Sales Order Line\nLn Item Number"
    slit = "Item Width(mm):1000\nSL Run Len(m)"
    rolls = "Ser T Rolls Width(mm) Tot Qty(M2)"
    confirm = "Please confirm update yes"
    price = "Sales Order Line\nList Price 100 Price 100"
    totals = "Order: SO123456\nLine Total: 100\nTotal Tax: 10"
    warning = "Press space bar to continue."
    done = "mfmenu Main Menu"
    pairs = [
        ("\r", "Create WO: Y Rework: Y"), (f1, line),
        ("TEST", None), (f1, "Site: CB2"), ("CB2", None),
        (f1, "Qty Ordered UM M2"), (f1, slit),
        (f1, slit), ("\r", slit), ("\r", slit), ("500\r", rolls),
        ("\r", rolls), ("1\r", rolls), ("1000\r", rolls),
        (f4, confirm), (f1, slit), (f4, confirm),
        (f1, "Sales Order Line\nPricing Date: 09/29/26"),
        (f1, price), (f1, price), ("100", None),
        (f1, "Tax Usage:"), (f1, "Transaction Comments"),
        (f4, line), (f4, totals),
    ]
    followups = {}
    if late_reason_code:
        # 実機ログの停止画面を参考にした合成条件。0.3秒の遅延は仮定であり実測ではない
        reason = "Sales Order Line\nLn Item Number\nReason Code\nList Price:\nRequest Date:\nPromise Date:"
        index = pairs.index((f4, line))
        followups[index] = (0.3, reason)
        pairs[index + 1:index + 1] = [("65\r", reason), ("28\r", reason), ("28\r", reason), (f1, line)]
    if early_warning:
        pairs += [(f1, warning), (" ", done)]
    elif no_warning:
        pairs += [(f1, totals), (f1, done)]
    else:
        pairs += [(f1, totals), (f1, warning), (" ", done)]
    # delay: 画面応答が届くまでの遅延。届く前に次のキーを送るとStrictReplayが失敗させる。
    # delayed: 遅延させる送信の番号（負数は末尾から）。None なら全送信を遅延させる。
    targets = None if delayed is None else {i % len(pairs) for i in delayed}
    replay = StrictReplay(line, [
        ExpectedSend(data, response,
                     delay if response is not None and (targets is None or index in targets) else 0.0,
                     followups.get(index))
        for index, (data, response) in enumerate(pairs)
    ])
    payload = {"items": [{"product_name": "TEST", "width": "1000", "length": "500",
                          "quantity": 1, "price": "100"}]}
    return replay, payload
