/**
 * MFG/PRO レポート汎用書き込み Web API (doPost)
 *
 * 自作モダンターミナルの addon_kit.add_sheet_report_button / send_rows_to_sheet から呼ばれます。
 * 既存の在庫・Complaint・受注残＆売上のGASとは別に、新しいウェブアプリとしてデプロイしてください。
 *
 * 受け付ける形式（どちらか一方）:
 *   1) フォーム POST : data=<Base64(UTF-8 の JSON)>   … 自作モダンターミナルの送信方式
 *   2) JSON 本文 POST: Content-Type: application/json
 *
 * JSON の内容:
 *   { "spreadsheetId": "...", "sheetName": "...", "data": [["見出し", ...], ["値", ...], ...] }
 *   （"menu" などその他の項目は無視します）
 *
 * 指定シートの全セルの値を消去（書式は保持）してから data を A1 から書き込みます。
 */

const LOCK_TIMEOUT_MS = 30000;
const MAX_CELL_CHARS = 50000;          // Google スプレッドシートの1セルの上限
const ALLOWED_SPREADSHEET_IDS = [];    // 空 = 制限なし。書き込み先を限定する場合は ID を列挙
const SPREADSHEET_ID_PATTERN = /^[A-Za-z0-9_-]{25,}$/;
const NUMBER_PATTERN = /^-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$/;  // 1,234.50 / -9582 など
const LEADING_ZERO_PATTERN = /^-?0\d/;                               // 00123 などのコード
const FORMULA_TRIGGER_PATTERN = /^[=+\-@]/;

function doPost(e) {
  let request;
  try {
    request = parseRequest(e);
  } catch (err) {
    return jsonResponse("error", err.message);
  }

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(LOCK_TIMEOUT_MS)) {
    return jsonResponse("error", "サーバーが混雑しています。しばらく待って再試行してください。");
  }
  try {
    const result = writeToSheet(request);
    return jsonResponse(
      "success",
      `シート「${result.sheet}」へ ${result.rows.toLocaleString()} 行 (${result.cols} 列) を書き込みました。`,
      result
    );
  } catch (err) {
    return jsonResponse("error", "GAS処理エラー: " + (err && err.message ? err.message : err));
  } finally {
    lock.releaseLock();
  }
}

function parseRequest(e) {
  const params = (e && e.parameter) || {};
  let json;
  if (params.data) {
    const bytes = Utilities.base64Decode(params.data.replace(/ /g, "+"));
    json = Utilities.newBlob(bytes).getDataAsString("UTF-8");
  } else if (e && e.postData && e.postData.contents) {
    json = e.postData.contents;
  } else {
    throw new Error("送信データがありません。");
  }

  let payload;
  try {
    payload = JSON.parse(json);
  } catch (err) {
    throw new Error("JSON を解析できません: " + err.message);
  }

  const spreadsheetId = String(payload.spreadsheetId || params.spreadsheetId || "").trim();
  const sheetName = String(payload.sheetName || params.sheetName || "").trim();
  const rows = payload.data;

  if (!SPREADSHEET_ID_PATTERN.test(spreadsheetId)) {
    throw new Error("spreadsheetId が正しくありません。");
  }
  if (ALLOWED_SPREADSHEET_IDS.length && ALLOWED_SPREADSHEET_IDS.indexOf(spreadsheetId) === -1) {
    throw new Error("このスプレッドシートへの書き込みは許可されていません。");
  }
  if (!sheetName) {
    throw new Error("sheetName が指定されていません。");
  }
  if (!Array.isArray(rows) || rows.length === 0 || !rows.every(Array.isArray)) {
    throw new Error("data は1行以上の二次元配列で指定してください。");
  }
  return { spreadsheetId, sheetName, rows };
}

function writeToSheet({ spreadsheetId, sheetName, rows }) {
  const sheet = SpreadsheetApp.openById(spreadsheetId).getSheetByName(sheetName);
  if (!sheet) {
    throw new Error(`シート「${sheetName}」が見つかりません。`);
  }
  const values = sanitizeRows(rows);
  const numRows = values.length;
  const numCols = values[0].length;

  sheet.clearContents();
  ensureSheetDimensions(sheet, numRows, numCols);
  sheet.getRange(1, 1, numRows, numCols).setValues(values);
  return { spreadsheetId, sheet: sheetName, rows: numRows, cols: numCols };
}

function sanitizeRows(rows) {
  const numCols = rows.reduce((max, row) => Math.max(max, row.length), 0);
  if (numCols === 0) {
    throw new Error("data に列がありません。");
  }
  return rows.map((row, rowIndex) => {
    const out = new Array(numCols);
    for (let c = 0; c < numCols; c++) {
      out[c] = sanitizeCell(row[c], rowIndex === 0);
    }
    return out;
  });
}

function sanitizeCell(value, isHeader) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isFinite(value) ? value : "";
  if (typeof value === "boolean") return value;

  let text = (typeof value === "string" ? value : JSON.stringify(value)).trim();
  if (!text) return "";

  if (!isHeader && NUMBER_PATTERN.test(text)) {
    if (!LEADING_ZERO_PATTERN.test(text)) {
      return Number(text.replace(/,/g, ""));
    }
    return "'" + text;
  }
  if (FORMULA_TRIGGER_PATTERN.test(text)) {
    text = "'" + text;
  }
  return text.length > MAX_CELL_CHARS ? text.slice(0, MAX_CELL_CHARS) : text;
}

function ensureSheetDimensions(sheet, requiredRows, requiredCols) {
  const maxRows = sheet.getMaxRows();
  const maxCols = sheet.getMaxColumns();
  if (requiredRows > maxRows) sheet.insertRowsAfter(maxRows, requiredRows - maxRows);
  if (requiredCols > maxCols) sheet.insertColumnsAfter(maxCols, requiredCols - maxCols);
}

function jsonResponse(status, message, extraData) {
  const body = Object.assign({ status, message, timestamp: new Date().toISOString() }, extraData || {});
  return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
}
