import customtkinter as ctk
import paramiko
import pyte
import threading
import time

# サーバー情報
HOST = "mfg03"
PORT = 22
USER = "takehik"
PASS = "nhy7mju8"

class TerminalApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # ウィンドウの基本設定
        self.title("My Modern Terminal - Powered by Python & CustomTkinter")
        self.geometry("1100x650")
        ctk.set_appearance_mode("dark")  # 流行りのダークモード
        ctk.set_default_color_theme("blue")
        
        # レイアウトの設定 (1行、2列)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ---------------- 左側のサイドバー (設定・操作パネル) ----------------
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="My Terminal", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 30))
        
        self.status_label = ctk.CTkLabel(self.sidebar_frame, text="🔴 未接続", text_color="gray")
        self.status_label.grid(row=1, column=0, padx=20, pady=10)
        
        self.connect_btn = ctk.CTkButton(self.sidebar_frame, text="サーバーへ接続", command=self.connect_to_server)
        self.connect_btn.grid(row=2, column=0, padx=20, pady=10)
        
        self.disconnect_btn = ctk.CTkButton(self.sidebar_frame, text="切断", command=self.disconnect_server, fg_color="#C62828", hover_color="#b71c1c")
        self.disconnect_btn.grid(row=3, column=0, padx=20, pady=10)
        self.disconnect_btn.configure(state="disabled")

        # ---------------- 右側のターミナル画面 ----------------
        # ハッカー風の黒背景・緑文字を設定
        self.textbox = ctk.CTkTextbox(
            self, 
            font=ctk.CTkFont(family="Consolas", size=14), 
            fg_color="#0C0C0C", 
            text_color="#00FF41", 
            wrap="none"
        )
        self.textbox.grid(row=0, column=1, padx=(10, 10), pady=(10, 10), sticky="nsew")
        
        # キーボード入力をキャッチするイベントバインド
        self.textbox.bind("<Key>", self.on_key_press)
        
        # 変数の初期化
        self.ssh = None
        self.shell = None
        self.is_connected = False
        
        # 仮想スクリーン (横132マス × 縦24マス)
        self.cols = 132
        self.rows = 24
        self.screen = pyte.Screen(self.cols, self.rows)
        self.stream = pyte.Stream(self.screen)
        
        self.update_job = None
        
        # 起動時のメッセージ
        welcome_msg = "=========================================================\n" \
                      "  Welcome to Modern Python Terminal Emulator!\n" \
                      "  左の「サーバーへ接続」ボタンを押してください。\n" \
                      "=========================================================\n"
        self.textbox.insert("1.0", welcome_msg)
        
    def connect_to_server(self):
        self.connect_btn.configure(state="disabled")
        self.status_label.configure(text="🟡 接続中...", text_color="yellow")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("end", f"[{HOST}] に SSH接続を試みています...\n")
        
        # フリーズを防ぐため、裏側（別スレッド）で接続処理を行う
        threading.Thread(target=self._connect_thread, daemon=True).start()

    def _connect_thread(self):
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=10)
            
            # サーバーに VT100 ターミナルとして振る舞うことを宣言
            self.shell = self.ssh.invoke_shell(term='vt100', width=self.cols, height=self.rows)
            self.is_connected = True
            
            # データ受信用の裏側ループを開始
            threading.Thread(target=self._receive_loop, daemon=True).start()
            
            # GUIの画面更新（アニメーション）を開始
            self.after(50, self._update_screen)
            
            self.status_label.configure(text="🟢 接続済み", text_color="#00FF41")
            self.disconnect_btn.configure(state="normal")
            
        except Exception as e:
            self.textbox.insert("end", f"\n❌ 接続エラー: {e}\n")
            self.connect_btn.configure(state="normal")
            self.status_label.configure(text="🔴 接続失敗", text_color="red")

    def _receive_loop(self):
        """ サーバーから流れてくる暗号(エスケープシーケンス)を受け取り続ける """
        while self.is_connected and self.shell:
            try:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(65535)
                    text = chunk.decode('utf-8', errors='ignore')
                    # 受け取った文字を仮想スクリーン(pyte)に流し込んでお絵描きさせる
                    self.stream.feed(text)
                else:
                    time.sleep(0.01)
            except Exception:
                break
        self.disconnect_server()

    def _update_screen(self):
        """ 仮想スクリーンの現在の状態を読み取って、画面のテキストボックスを毎秒上書きする """
        if not self.is_connected:
            return
            
        # 仮想スクリーンに描かれた24行の配列を取得
        lines = self.screen.display
        
        # 画面のちらつきを防ぎながら一気に書き換える
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", "\n".join(lines))
        
        # 50ミリ秒後にまた自分自身を呼び出す（パラパラ漫画の要領）
        self.update_job = self.after(50, self._update_screen)

    def on_key_press(self, event):
        """ ユーザーがキーボードを叩いた時に発動 """
        if not self.is_connected or not self.shell:
            return "break"
            
        char = event.char
        keysym = event.keysym
        
        send_data = ""
        
        # --- 特殊キーを VT100 の信号に翻訳する ---
        if keysym == "Return":
            send_data = "\r"
        elif keysym == "BackSpace":
            send_data = "\b"
        elif keysym == "Escape":
            send_data = "\x1b"
        elif keysym == "F1":
            send_data = "\x1bOP"
        elif keysym == "F2":
            send_data = "\x1bOQ"
        elif keysym == "F3":
            send_data = "\x1bOR"
        elif keysym == "F4":
            send_data = "\x1bOS"
        elif char: # 普通の文字(a, b, c...)
            send_data = char
            
        # サーバーへ信号を送信！
        if send_data:
            try:
                self.shell.send(send_data)
            except Exception:
                pass
                
        # Tkinter本来の「文字を入力する機能」を無効化する
        # （サーバーからエコーバックされてくる文字を表示するため）
        return "break"

    def disconnect_server(self):
        self.is_connected = False
        if self.update_job:
            self.after_cancel(self.update_job)
            self.update_job = None
        if self.shell:
            self.shell.close()
        if self.ssh:
            self.ssh.close()
            
        self.connect_btn.configure(state="normal")
        self.disconnect_btn.configure(state="disabled")
        self.status_label.configure(text="🔴 未接続", text_color="gray")
        
        # 画面に切断メッセージを残す
        lines = self.screen.display
        lines.append("\n\n--- サーバーとの接続が切断されました ---")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", "\n".join(lines))

if __name__ == "__main__":
    app = TerminalApp()
    app.mainloop()
