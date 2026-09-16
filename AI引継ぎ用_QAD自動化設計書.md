# QAD/MFG:PRO Automation & GAS Submission Blueprint (v2)
**[Target Audience: AI Coding Assistants / Developers]**

このドキュメントは、Python を使用して「社内サーバー（QAD等のVT100ターミナルエミュレータ）へSSH接続し、処理結果をブラウザ経由でGoogle Apps Script (GAS) へ送信する」ツールを作成するための標準化された設計書およびAI向けの実装ガイドラインです。

以後の開発で同様のツールを構築する際は、本ドキュメントの設計思想と回避済みの罠（Pitfalls）を必ず遵守して実装してください。

---

## 1. サーバーサイドとの対話 (Terminal Interaction)
社内システムはレガシーな VT100 ターミナルで動作しており、通常のCLIコマンド送信ではなく、人間が行うキーストロークをシミュレートする必要があります。

### 1-1. SSH接続とシェル設定
- `paramiko` の `invoke_shell` を使用し、ターミナル幅を広く確保します。
- `term='vt100', width=132, height=24` の指定が必須です（データ出力の折り返しを防ぐため）。

### 1-2. キーストローク送信の注意点
- **[罠]** コマンド間の待機時間（`time.sleep`）を削ると、サーバー側（QAD）のパケット処理が追いつかず文字落ち（キーストロークの喪失）が発生します。
- **[対策]** 各コマンド（フィールドへの値入力）の間に `time.sleep(1.0)` を挿入して安全を担保します。
- **[補足]** 1つのフィールドに値を入力する際の `shell.send("1FGI\r")` 自体は一括送信で問題ありません。文字を1文字ずつ `time.sleep(0.1)` で送る必要はありません（テスト済み）。**重要なのは「コマンド間」のsleepであり、「文字間」のsleepではありません。**

### 1-3. 特殊キーの送信
- 決定（Enter）: `\r` を使用します。`\n` は使用しないでください。
- 実行（F1キー）: QADにおける「Go」や「抽出開始」にあたる F1 キーは `\x1bOP` を送信します。
- ページ送り（Space）: 「Press space bar to continue」の画面では、**絶対に `\r` を含めず `" "`（スペースのみ）** を送信してください。余分な `\r` は次の画面（メニュー画面等）に持ち越され、「Invalid Choice」エラーを引き起こします。
- Ctrl+F: `\x06` を送信します。一部の画面で確認ダイアログ等の応答に使用します。

---

## 2. スマートウェイト (Smart Waiting)
固定の `time.sleep()` ではなく、画面に特定のプロンプトが出現するまで待機するスマートウェイトを実装します。

### 2-1. wait_for_text の実装
- `shell.recv_ready()` を監視し、バッファに特定のテキスト（例: `"Item Number"`, `"Please select a function"`）が含まれているか確認します。
- **[罠]** 受信データには大量の ANSI エスケープシーケンス（カーソル移動や色付け等の制御文字）が含まれるため、単純な文字列検索はマッチしません。
- **[対策]** 判定前に必ず正規表現で制御文字を除去（Clean up）してください。
  ```python
  ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
  clean_buf = ansi_escape.sub('', buffer).replace('\x00', '')
  ```

---

## 3. データ取得方式：winPrint＋SFTP (推奨) ⚠️ 最重要

### 3-1. 概要
画面からのリアルタイム受信ではなく、**サーバー内ファイル出力（winPrint）＋ SFTPダウンロード** を使用します。これが現在の標準方式です。

### 3-2. winPrint とは
QAD のレポート画面には「Output」フィールドがあり、デフォルトは `local`（画面出力）です。ここに `winPrint` と入力して実行すると、レポート全体が `/home/takehik/winPrint` というテキストファイルとしてサーバー上に書き出されます。画面描画を完全にスキップするため、数万件のデータでも一瞬で出力されます。

### 3-3. 画面ごとの Output フィールドへの到達方法 ⚠️ 最重要
**QADの各レポート画面によって、Output フィールドへのカーソル移動方法が異なります。** これを間違えると winPrint が入力されず、遅い画面出力モードにフォールバックします。

| レポート | 画面番号 | Output欄への到達方法 |
|---------|---------|-------------------|
| 在庫スナップショット | 99.3.6.1 | 条件入力後に **F1キーを1回押す** とOutput欄にジャンプする |
| 在庫移動明細 | 99.3.21.4 | F1キーを押すと即座にレポート実行されてしまうため、**Lot入力後にEnterキーを11回**送って1フィールドずつOutput欄まで移動する |

**[罠]** 99.3.21.4 でEnterの回数を間違えると（例: 15回）、Output欄を通り過ぎてしまい、`Output: local`（デフォルト）のまま実行され、画面出力モードになります。正しいEnter回数は画面のフィールド構造から正確に計算する必要があります。

**99.3.21.4 のフィールド構造（全26フィールド）:**
```
1-2:   Item Number (From/To)
3-4:   Site (From/To)
5-6:   Effective Date (From/To)
7-8:   Prod Line (From/To)
9-10:  Order (From/To)
11-12: Customer (From/To)
13-14: Lot (From/To)
15-16: Pallet (From/To)
17-18: Shipper (From/To)
19-20: ID (From/To)
21-22: Type (From/To)
23-24: Location (From/To)
25:    Only Show On Hand (Yes/No)
26:    ★ Output ← ここに winPrint を入力
```
Lot（フィールド14）の入力後、残り11フィールド（15〜25）をEnterでスキップすると、フィールド26（Output）にカーソルが到達します。

### 3-4. Progressデータベースエンジンのバッファリング ⚠️
- **[罠]** QADの基盤である Progress データベースエンジンは、ファイル出力をメモリ上でバッファリングします。クエリが完了するまで winPrint ファイルは **0バイトのまま** で、完了した瞬間に一気にデータが書き込まれます。
- **[対策]** ファイルサイズの監視ループでは、`size > 0` になるまで辛抱強く待ちます。タイムアウトは **600秒（10分）** を設定してください（半年分の在庫移動明細など重いクエリ対応）。
- サイズが `> 0` になった後は、**2秒間サイズ変化なし**（`stable_count >= 4` at 0.5秒間隔）で書き込み完了と判定します。

### 3-5. SFTPダウンロードの注意事項
- **[罠]** `sftp.file(remote, 'rb').read()` を使うと、5MB超のファイルで Paramiko がデッドロック（ハングアップ）します。これは Paramiko の既知のバグです。
- **[対策]** 必ず `sftp.get(remote_path, local_temp_path)` で一旦ローカルの一時ファイルに保存し、その後 `open(local_temp_path, 'rb').read()` で読み込んでください。
- **[リソース管理]** `sftp.close()` を正常時・エラー時の両方で必ず呼び出してください。

### 3-6. winPrint ファイルの事前削除
- 実行開始時に `ssh.exec_command("rm -f /home/takehik/winPrint")` で前回の残骸を削除します。
- これにより、ファイルの存在＝今回のクエリの出力、と判定できるようになります。

---

## 4. データの解析 (Data Parsing)

### 4-1. マルチバイト文字の処理
- ターミナルの文字コードは `utf-8` ではなく **`cp932` (Shift_JIS)** を指定してください（日本語環境のQAD特有）。
- デコード時は `errors='replace'` を指定して不正バイトによるクラッシュを防ぎます。

### 4-2. カラムの切り出し (Byte-width Slicing) ⚠️ 最重要
- レポートは固定幅の表形式（例: `--- --- ---` で区切られる）で出力されますが、データ行に半角カナ（`ﾀｶﾗ`等）や全角漢字が混ざると、Pythonの `len()` と実際のターミナル表示幅がズレます。
- **[罠]** 文字列ベース（インデックス）で `line[start:end]` と切り出すと、日本語が含まれる行以降のカラムがすべて数文字分ズレて破綻します。
- **[対策]** スライス位置の特定と切り出しは、**必ず行を `encode('cp932')` でバイト列にしてから行い、バイト幅で切り出した後に `decode('cp932')` で文字列に戻す** 処理を実装してください。

### 4-3. レポート末尾の不要データ除去
- レポートの最終行 `End of Report` 以降には「Report Criteria（抽出条件の一覧）」が出力されます。これはデータではないため、パース時に `"End of Report" in line` を検出した時点で `break` してください。

### 4-4. 日付フォーマットの変換
- QAD は日付を `MM/DD/YY`（例: `08/30/26`）で出力します。GAS や日本の業務で使いやすいよう `YYYY/MM/DD`（例: `2026/08/30`）に変換してください。

---

## 5. GASへのデータ転送 (GAS POST via Browser)
Python から Google Apps Script (GAS) へ抽出したデータを転送します。

### 5-1. ブラウザを経由する理由
- Python の `requests` ライブラリを使用して直接 POST した場合、Google Workspace の認証や社内SSO・プロキシに弾かれ、`401 Unauthorized` やログインページHTMLが返却されて失敗します。
- **[対策]** 認証済みのセッションを持つユーザーの標準ブラウザ（Chrome/Edge）を利用し、ローカルに生成した HTML の非表示フォーム（Hidden Form）から自動で `POST` 送信する手法を採用します。

### 5-2. 転送フローと即時クローズ
1. 抽出した2次元配列データを JSON に変換し、安全のため `Base64` エンコードします。
2. HTML 内の `form`（`method="POST" action="GAS_URL"`）に値を埋め込みます。
3. `body onload` で JavaScript を用いて自動で `form.submit()` を実行します。
4. **[即時クローズ]** GAS側の処理（数万件のスプレッドシート書き込み等）には数分かかる場合があります。レスポンスを待つとユーザー体験を損ねるため、`submit()` 発行から3〜5秒後に `window.close()` を実行し、ブラウザのタブを強制的に閉じます。

### 5-3. HTML テンプレート例
```html
<script>
    function send() {{
        document.getElementById('postForm').submit();
        setTimeout(function() {{
            window.opener = null;
            window.open('', '_self');
            window.close();
        }}, 3000); // 3秒後に自動クローズ
    }}
</script>
<body onload="send()">
    <iframe name="hidden_iframe" style="display:none;"></iframe>
    <form id="postForm" method="POST" action="{GAS_URL}" target="hidden_iframe">
        <input type="hidden" name="data" value="{b64_data}">
    </form>
</body>
```

---

## 6. GAS URL 一覧

| 用途 | URL |
|------|-----|
| 在庫（Inventory） | `https://script.google.com/a/macros/ap.averydennison.com/s/AKfycbwS6dZ9umUKP71NGieiW_tDffygGtAFHKOAxyAo7cWDe3T_xMxlISSdmXoNlK6TaENfkA/exec` |
| Complaint | `https://script.google.com/a/macros/ap.averydennison.com/s/AKfycbyEwl3D8kjtbkk34V_9aJGrlgt39B480O_W3zCI6JiSC4glpS4XNj6JSC4ZiyMNKA/exec` |

---

## 7. サーバー安全性の保証
本ツールがサーバー上で行う書き込み操作は **`rm -f /home/takehik/winPrint` の1つだけ** です。
- パスは完全にハードコード（固定値）されており、変数展開やワイルドカードは使用していません
- `rm -rf`（ディレクトリ削除）は使用していません
- `sftp.put()`（アップロード）は使用していません
- 他のユーザーのファイル、システムファイル、データベースには一切アクセスしません

---

## 8. 現在のツール構成

| ツール名 | 対象レポート | 画面番号 | ファイルパス |
|---------|------------|---------|------------|
| 全自動在庫レポート抽出＆GAS送信ツール | 在庫スナップショット | 99.3.6.1 | `C:\Users\0138018\.antigravity\全自動在庫レポート抽出＆GAS送信ツール.py` |
| Complaint送信 | 在庫移動明細 | 99.3.21.4 | `C:\Users\0138018\.antigravity\Complaint送信.pyw` |

### 主な技術的差異

| 項目 | 在庫ツール (99.3.6.1) | Complaint (99.3.21.4) |
|------|----------------------|----------------------|
| UI | CUIコンソール (print) | GUI (customtkinter) |
| Output欄への移動 | F1キー1回でジャンプ | Enterキー11回で移動 |
| ターミナル幅 | width=256 | width=132 |
| GUIステータス表示 | なし（コンソール出力） | あり（[1/6]〜[6/6]リアルタイム表示） |
