import os
import subprocess
import sys
from pathlib import Path

repo_dir = Path(r"c:\Users\0138018\.antigravity\mfgpro_controller")
docs_dir = repo_dir / "docs"
html_path = docs_dir / "manual_print.html"
pdf_path_repo = docs_dir / "QAD_99_7_1_1_Order_Entry_Manual.pdf"
pdf_path_desktop = Path(r"C:\Users\0138018\Desktop\QAD_99_7_1_1_受注入力完全仕様マニュアル.pdf")

edge_exe = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

html_content = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>QAD 99.7.1.1 受注入力 完全自動化仕様マニュアル</title>
<style>
  @page {
    size: A4 portrait;
    margin: 14mm 12mm 14mm 12mm;
    @bottom-right {
      content: counter(page);
    }
  }
  body {
    font-family: "Segoe UI", "Yu Gothic", "Meiryo", sans-serif;
    color: #1e293b;
    background-color: #ffffff;
    line-height: 1.6;
    font-size: 10.5pt;
    margin: 0;
    padding: 0;
  }
  h1 {
    font-size: 20pt;
    color: #0f172a;
    border-bottom: 3px solid #0284c7;
    padding-bottom: 6px;
    margin-top: 0;
    margin-bottom: 4px;
  }
  .subtitle {
    font-size: 11pt;
    color: #64748b;
    margin-bottom: 20px;
    font-weight: 600;
  }
  h2 {
    font-size: 14pt;
    color: #0369a1;
    border-left: 5px solid #0284c7;
    padding-left: 8px;
    margin-top: 22px;
    margin-bottom: 10px;
    page-break-after: avoid;
  }
  h3 {
    font-size: 12pt;
    color: #334155;
    margin-top: 14px;
    margin-bottom: 6px;
    page-break-after: avoid;
  }
  p, ul, ol {
    margin-top: 4px;
    margin-bottom: 8px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 16px 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
  }
  th, td {
    border: 1px solid #cbd5e1;
    padding: 6px 9px;
    text-align: left;
  }
  th {
    background-color: #f1f5f9;
    color: #0f172a;
    font-weight: bold;
  }
  tr:nth-child(even) td {
    background-color: #f8fafc;
  }
  .important-box {
    background-color: #eff6ff;
    border-left: 4px solid #2563eb;
    padding: 10px 14px;
    margin: 12px 0;
    border-radius: 4px;
    font-size: 9.5pt;
  }
  .warning-box {
    background-color: #fef2f2;
    border-left: 4px solid #ef4444;
    padding: 10px 14px;
    margin: 12px 0;
    border-radius: 4px;
    font-size: 9.5pt;
  }
  .code-block {
    background-color: #0f172a;
    color: #f8fafc;
    padding: 10px 14px;
    border-radius: 6px;
    font-family: "Consolas", monospace;
    font-size: 8.5pt;
    white-space: pre-wrap;
    word-break: break-all;
    margin: 8px 0;
    page-break-inside: avoid;
  }
  .flow-container {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 14px;
    margin: 12px 0;
    page-break-inside: avoid;
  }
  .flow-step {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-left: 5px solid #0284c7;
    border-radius: 4px;
    padding: 8px 12px;
    margin-bottom: 8px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
  }
  .flow-step.order-id {
    border-left-color: #10b981;
    background-color: #f0fdf4;
  }
  .flow-step-title {
    font-weight: bold;
    font-size: 10pt;
    color: #0f172a;
  }
  .flow-step-desc {
    font-size: 9pt;
    color: #475569;
    margin-top: 2px;
  }
  .flow-arrow {
    text-align: center;
    color: #0284c7;
    font-weight: bold;
    font-size: 11pt;
    margin: -4px 0 4px 0;
  }
  .badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 8pt;
    font-weight: bold;
    color: #ffffff;
  }
  .badge-primary { background-color: #0284c7; }
  .badge-success { background-color: #059669; }
  .badge-warning { background-color: #d97706; }
  .badge-dark { background-color: #475569; }
  .page-break {
    page-break-before: always;
  }
</style>
</head>
<body>

<h1>QAD 99.7.1.1 受注入力 完全自動化仕様マニュアル</h1>
<div class="subtitle">AI指示用プロンプト・リファレンス ＆ システム開発・運用統合仕様書</div>

<h2>1. システム概要と基本設計思想</h2>
<p>本仕様書は、Progress 4GL / QAD CUI 端末（VT100 80桁×24行）における <strong>99.7.1.1 (Sales Order Maintenance / xxsosomt.p)</strong> の自動入力を100%正確・安全に完遂するための完全リファレンスです。</p>

<div class="important-box">
  <strong>【最重要原則 1】ブラインド送信（先走り送信 / Typeahead）の絶対禁止</strong><br>
  Progress 4GLはサーバー側のDBトランザクションや画面描画により、ステップ間でコンマ数秒〜数秒の応答ラグが発生します。レスポンスを待たずに送信するとキー脱字や誤爆の原因となるため、<strong>必ず画面バッファの表示変化（固有のプロンプト・ポップアップ枠・カーソル位置）を検知してから次キー・データを送信（同期待ち受け制御）</strong>します。
</div>

<div class="important-box">
  <strong>【最重要原則 2】Order ID（受注番号）の自動採番と一連IDの管理</strong><br>
  Step 1 の <code>Order:</code> 入力欄を空のまま Enter を送信すると、QADサーバー側で一意の最新番号（例: <code>SO199302</code>）が自動採番されます。<br>
  <strong>この採番された Order ID が、当該注文におけるヘッダー・全明細行・特記事項・最終合計を束ねる一連の共通管理ID</strong>となります。
</div>

<div class="warning-box">
  <strong>【安全保護】メンテナンス画面とレポート自動Excel出力の完全分離</strong><br>
  99.7.1.1 などの入力・保守画面（<code>*mt.p</code>）のテーブル罫線（<code>│─── ───│</code>）をレポート集計表と誤認して勝手にExcelが起動しないよう、画面判定ロジックにより厳格に除外ガードされています。
</div>

<h2>2. 全体統合フロー (Step 1 〜 Step 6.3.0)</h2>
<div class="flow-container">

  <div class="flow-step">
    <div class="flow-step-title"><span class="badge badge-dark">START</span> QAD メインメニュー (mfmenu)</div>
    <div class="flow-step-desc">キー送信: <code>99.7.1.1 + &lt;Enter&gt;</code> ➔ 画面に <code>Order:</code> が出現するまで待機</div>
  </div>
  <div class="flow-arrow">▼</div>

  <div class="flow-step order-id">
    <div class="flow-step-title"><span class="badge badge-success">STEP 1</span> Order番号自動採番 ＆ ヘッダー画面着地</div>
    <div class="flow-step-desc">
      キー送信: <code>&lt;Enter&gt;</code> (空のまま送信)<br>
      <strong>★動作: サーバー側で最新 Order ID (例: SO199302) が自動採番（一連の共通注文管理ID）</strong><br>
      画面待機: Sold-To 入力欄 (Row 3, Col 29) へのカーソル着地を検知
    </div>
  </div>
  <div class="flow-arrow">▼</div>

  <div class="flow-step">
    <div class="flow-step-title"><span class="badge badge-primary">STEP 2</span> 受注ヘッダー一括貼り付け (10行改行結合)</div>
    <div class="flow-step-desc">
      データ送信: Sold-To 欄から 10行改行結合テキストを一括ペースト<br>
      (Sold-To ➔ <strong>Bill-To(同値)</strong> ➔ Ship-To ➔ Order Date ➔ Req Date ➔ Promise空 ➔ Due Date ➔ Perform空 ➔ PO番号 ➔ 備考)<br>
      キー送信: <code>&lt;F1&gt;</code> (ヘッダー確定) ➔ 画面下に <code>Category=... Press space bar</code> が出た場合は <code>&lt;Space&gt;</code> 送信
    </div>
  </div>
  <div class="flow-arrow">▼</div>

  <div class="flow-step">
    <div class="flow-step-title"><span class="badge badge-primary">STEP 3</span> 税金設定ポップアップ (Tax Information)</div>
    <div class="flow-step-desc">画面待機: <code>Tax Usage:</code> ポップアップ枠検知 ➔ キー送信: <code>&lt;F1&gt;</code> (スキップ)</div>
  </div>
  <div class="flow-arrow">▼</div>

  <div class="flow-step">
    <div class="flow-step-title"><span class="badge badge-primary">STEP 4</span> ヘッダー追加画面 (Salesperson / Freight 等)</div>
    <div class="flow-step-desc">画面待機: <code>Salesperson:</code> 画面検知 ➔ キー送信: <code>&lt;F1&gt;</code> (スキップ)</div>
  </div>
  <div class="flow-arrow">▼</div>

  <div class="flow-step">
    <div class="flow-step-title"><span class="badge badge-primary">STEP 5</span> 特記事項 (Transaction Comments)</div>
    <div class="flow-step-desc">
      画面待機: <code>Transaction Comments</code> 画面検知<br>
      特記事項あり: <code>&lt;F1&gt;</code> ➔ 各行本文入力 ➔ <code>&lt;F1&gt;</code> ➔ Print on quote で <code>&lt;F1&gt;</code> ➔ <code>&lt;F4&gt;</code> (明細へ)<br>
      特記事項なし: そのまま <code>&lt;F4&gt;</code> (明細へ)
    </div>
  </div>
  <div class="flow-arrow">▼</div>

  <div class="flow-step">
    <div class="flow-step-title"><span class="badge badge-warning">STEP 6</span> 受注明細行入力 (Line Items / 6.1.0 〜 6.2.5)</div>
    <div class="flow-step-desc">
      <strong>【第1階層: 品番ループ】</strong><br>
      ・6.1.0: Ln欄で <code>&lt;Enter&gt;</code> (行番号 1, 2... 自動採番)<br>
      ・6.1.1: <code>Create WO: Y</code> ポップアップを <code>&lt;F1&gt;</code> でスキップ<br>
      ・6.1.3: Item Number欄に品番入力 + <code>&lt;F1&gt;</code> ➔ <code>Site</code> 枠検知 ➔ <code>"CB2"</code> + <code>&lt;F1&gt;</code><br>
      ・6.1.4: <code>Qty Ordered UM</code> を <code>&lt;F1&gt;</code> でスキップ (平米数は自動計算)<br>
      <br>
      <strong>【第2階層: 長さ(SL)ループ】</strong><br>
      ・6.1.4-SL: <code>&lt;F1&gt;</code> でサブライン (SL 1, 2...) 採番 ➔ <code>Len(m)</code> 欄待機<br>
      ・6.2.0: 長さ入力 + <code>&lt;F1&gt;</code> ➔ <code>Ser T Rolls Width</code> ポップアップ待機<br>
      <br>
      <strong>【第3階層: 幅・本数(Ser/Rolls)ループ】</strong><br>
      ・6.2.1: <code>&lt;F1&gt;</code> (Serスキップ) ➔ Rolls欄に本数 + <code>&lt;Enter&gt;</code> ➔ Width欄に幅 + <code>&lt;Enter&gt;</code><br>
      ・同長さで別幅があれば繰り返し ➔ 次行Serで <code>&lt;F4&gt;</code> ➔ <code>Please confirm update</code> を <code>&lt;F1&gt;</code> ("yes") 確定 ➔ SL一覧へ復帰<br>
      <br>
      <strong>【品番完了＆単価入力】</strong><br>
      ・全長さ完了後: SL一覧画面で <code>&lt;F4&gt;</code> ➔ <code>Please confirm update</code> を <code>&lt;Enter&gt;</code> 確定<br>
      ・6.2.3: <code>Pricing Date</code> を <code>&lt;F1&gt;</code> でスキップ<br>
      ・6.2.4: <code>List Price</code> を <code>&lt;F1&gt;</code> でスキップ ➔ <code>Price</code> 欄に単価入力 + <code>&lt;F1&gt;</code><br>
      ・6.2.5: <code>Tax Usage</code> を <code>&lt;F1&gt;</code> スキップ ➔ <code>Transaction Comments</code> を <code>&lt;F1&gt;</code> スキップ ➔ 6.1.0 メインメニュー復帰
    </div>
  </div>
  <div class="flow-arrow">▼</div>

  <div class="flow-step">
    <div class="flow-step-title"><span class="badge badge-success">STEP 6.3.0</span> 受注最終合計画面 (Order Totals) ＆ 注文確定</div>
    <div class="flow-step-desc">
      全品番完了後: メインメニューで <code>&lt;F4&gt;</code> (または <code>&lt;F2&gt;</code> 2回) を送信<br>
      画面待機: <code>Line Total:</code> / <code>Total Tax:</code> 画面検知<br>
      キー送信: 1回目 <code>&lt;F1&gt;</code> ➔ 画面確認後 2回目 <code>&lt;F1&gt;</code> (注文保存)<br>
      画面待機: <code>Press space bar to continue</code> 検知 ➔ <strong>スペースキー <code>" "</code> (改行なし) 送信</strong> ➔ メインメニューへ安全復帰
    </div>
  </div>

</div>

<div class="page-break"></div>

<h2>3. ヘッダー一括貼り付け仕様 (Step 2 バッファ)</h2>
<p>Sold-To 欄にフォーカスがある状態で、以下の改行区切りテキストを一括ペーストします。</p>

<table>
  <thead>
    <tr>
      <th style="width:10%;">行</th>
      <th style="width:25%;">項目名</th>
      <th style="width:30%;">設定値ルール</th>
      <th style="width:35%;">説明・留意事項</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Line 1</td>
      <td><strong>Sold-To</strong></td>
      <td><code>customer_code</code></td>
      <td>顧客コード（例: "20019500"）</td>
    </tr>
    <tr>
      <td>Line 2</td>
      <td><strong>Bill-To</strong></td>
      <td><code>customer_code</code></td>
      <td><strong>【重要】Sold-To と同一の顧客コードを入力</strong></td>
    </tr>
    <tr>
      <td>Line 3</td>
      <td><strong>Ship-To</strong></td>
      <td><code>ship_to_code</code></td>
      <td>納品先コード（例: "20019583"）</td>
    </tr>
    <tr>
      <td>Line 4</td>
      <td><strong>Order Date</strong></td>
      <td>当日日付 (MM/dd/yy)</td>
      <td>システム当日付（例: "09/28/26"）</td>
    </tr>
    <tr>
      <td>Line 5</td>
      <td><strong>Required Date</strong></td>
      <td>要求納期 (MM/dd/yy)</td>
      <td>サイドバー入力値（例: "10/09/26"）</td>
    </tr>
    <tr>
      <td>Line 6</td>
      <td><strong>Promise Date</strong></td>
      <td><code>""</code> (空行)</td>
      <td>Enterでスキップ</td>
    </tr>
    <tr>
      <td>Line 7</td>
      <td><strong>Due Date</strong></td>
      <td>回答納期 (MM/dd/yy)</td>
      <td>サイドバー入力値（例: "10/07/26"）</td>
    </tr>
    <tr>
      <td>Line 8</td>
      <td><strong>Perform Date</strong></td>
      <td><code>""</code> (空行)</td>
      <td>Enterでスキップ</td>
    </tr>
    <tr>
      <td>Line 9</td>
      <td><strong>Purchase Order</strong></td>
      <td><code>purchase_order</code></td>
      <td>注文番号 / 発注番号（例: "YPW284"）</td>
    </tr>
    <tr>
      <td>Line 10</td>
      <td><strong>Remarks</strong></td>
      <td><code>remarks</code></td>
      <td>備考テキスト（例: "10/9 DC"）</td>
    </tr>
  </tbody>
</table>

<h2>4. 明細 3階層グループ化ロジック (Step 6)</h2>
<p>サイドバーから渡された注文データ（<code>items</code>）は、以下の階層構造に変換されてQADに登録されます。</p>

<div class="code-block">[
  {
    "line_no": 1,              /* 第1階層: Ln (品番ごとに1行採番) */
    "product_name": "OZS200",
    "price": "320.00",         /* 単価 (製品単位で一意) */
    "length_groups": [
      {
        "sl": 1,               /* 第2階層: SL (長さごとに採番) */
        "length": "600",
        "entries": [
          {"ser": 1, "rolls": 2, "width": "105"},  /* 第3階層: ロール (幅・本数) */
          {"ser": 2, "rolls": 1, "width": "150"}
        ]
      }
    ]
  }
]</div>

<h2>5. AI 指示用プロンプト・テンプレート</h2>
<p>将来別のAIエージェントに機能追加や改修を指示する際は、以下の枠内プロンプトをそのまま活用できます。</p>

<div class="code-block">あなたは Progress 4GL / QAD CUI 端末（VT100）の自動化エキスパートです。
以下の仕様書に完全に従い、QAD 99.7.1.1 (Sales Order Maintenance) の自動入力処理を実装・改修してください。

【厳格な遵守事項】
1. ブラインド送信の禁止:
   各ステップ間を移動する際、必ずターミナル画面バッファの表示変化（特定のプロンプト文字列・ポップアップ枠・カーソル位置）を待機してから次のキーストローク・値を送信してください。
2. Order ID の共通管理:
   Step 1 で Order 欄を空のまま Enter を送信すると自動採番される最新番号（例: SO199302）が、この注文の一連の共通管理IDです。
3. ヘッダー一括貼り付け:
   Step 2 では Sold-To 欄から 10行改行結合テキストを一括ペーストしてください。Line 2 の Bill-To には Sold-To と同一の顧客コードを入力してください。
4. 明細 3階層グループ化:
   Step 6 の明細データは「品番 (Ln)」➔「長さ (SL)」➔「幅・本数 (Ser/Rolls)」の階層構造でグループ化して順次登録してください。
5. 最終復帰の安全性:
   Step 6.3.0 の最終確定後、'Press space bar to continue' に対してはスペースキー（' '）のみを送信し、決して改行（\\r）を送らないでください。
6. レポート自動Excel展開の誤爆防止:
   99.7.1.1 などのメンテナンス画面（*mt.p）は、レポート自動Excel展開ロジックから必ず除外してください。</div>

</body>
</html>
"""

html_path.write_text(html_content, encoding="utf-8")
print(f"HTML written to {html_path}")

cmd = [
    str(edge_exe),
    "--headless",
    "--disable-gpu",
    f"--print-to-pdf={pdf_path_repo}",
    str(html_path)
]
print("Running Edge print-to-pdf...")
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0:
    print(f"PDF generated at: {pdf_path_repo}")
    import shutil
    shutil.copy2(pdf_path_repo, pdf_path_desktop)
    print(f"PDF copied to Desktop: {pdf_path_desktop}")
else:
    print(f"Edge error: {res.stderr}")
