import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [dataPath, outputPath, previewPath] = process.argv.slice(2);
if (!dataPath || !outputPath || !previewPath) {
  console.error("Usage: node generate_xlsx.mjs <meeting_data.json> <output.xlsx> <preview.png>");
  process.exit(2);
}

const data = JSON.parse(await fs.readFile(dataPath, "utf8"));
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Action Items");
sheet.showGridLines = false;
sheet.tabColor = "#195B7A";

sheet.getRange("A2:H2").merge();
sheet.getRange("A2").values = [["Action Items từ biên bản cuộc họp"]];
sheet.getRange("A2:H2").format = {
  font: { name: "Arial", size: 15, bold: true, color: "#15394A" },
  verticalAlignment: "center",
};
sheet.getRange("A3:H3").merge();
sheet.getRange("A3").values = [[`${data.title} | ${data.meeting_date || "Ngày họp chưa nêu"}`]];
sheet.getRange("A3:H3").format = { font: { name: "Arial", size: 10, italic: true, color: "#5D6B78" } };
sheet.getRange("A4:D4").values = [["Tổng công việc", data.action_items.length, "Cần rà soát", data.action_items.filter((x) => x.review_status !== "Đã xác định").length]];
sheet.getRange("A4:D4").format.font = { name: "Arial", size: 10 };
sheet.getRange("A4").format.font = { name: "Arial", size: 10, bold: true, color: "#195B7A" };
sheet.getRange("C4").format.font = { name: "Arial", size: 10, bold: true, color: "#8A5A00" };

const headers = ["ID", "Công việc", "Người phụ trách", "Email", "Deadline", "Dẫn chứng", "Trạng thái", "Lý do rà soát"];
const items = data.action_items.length ? data.action_items : [{
  id: "", task: "Không có Action Item rõ ràng trong nguồn.", owner: "", owner_email: "",
  deadline_text: "", evidence_ref: "", evidence_quote: "", review_status: "", review_reasons: [],
}];
const rows = items.map((item) => [
  item.id,
  item.task,
  item.owner,
  item.owner_email,
  item.deadline_iso ? new Date(`${item.deadline_iso}T00:00:00`) : item.deadline_text,
  item.evidence_ref ? `${item.evidence_ref}: “${item.evidence_quote}”` : "",
  item.review_status,
  (item.review_reasons || []).join("; "),
]);
sheet.getRange("A6:H6").values = [headers];
sheet.getRangeByIndexes(6, 0, rows.length, headers.length).values = rows;
const endRow = 6 + rows.length;
const table = sheet.tables.add(`A6:H${endRow}`, true, "ActionItemsTable");
table.style = "TableStyleMedium2";
table.showFilterButton = true;

sheet.getRange(`A6:H${endRow}`).format.font = { name: "Arial", size: 10 };
sheet.getRange("A6:H6").format = {
  fill: "#195B7A",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "inside", style: "thin", color: "#FFFFFF" },
};
sheet.getRange(`A7:H${endRow}`).format.verticalAlignment = "top";
sheet.getRange(`B7:B${endRow}`).format.wrapText = true;
sheet.getRange(`F7:H${endRow}`).format.wrapText = true;
sheet.getRange(`E7:E${endRow}`).format.numberFormat = "yyyy-mm-dd";
sheet.getRange(`G7:G${endRow}`).conditionalFormats.add("containsText", {
  text: "Cần rà soát",
  format: { fill: "#FFF1CC", font: { bold: true, color: "#8A5A00" } },
});

sheet.getRange("A:A").format.columnWidth = 8;
sheet.getRange("B:B").format.columnWidth = 42;
sheet.getRange("C:C").format.columnWidth = 22;
sheet.getRange("D:D").format.columnWidth = 28;
sheet.getRange("E:E").format.columnWidth = 16;
sheet.getRange("F:F").format.columnWidth = 50;
sheet.getRange("G:G").format.columnWidth = 18;
sheet.getRange("H:H").format.columnWidth = 36;
sheet.getRange(`A7:H${endRow}`).format.autofitRows();
sheet.getRange("2:2").format.rowHeight = 26;
sheet.freezePanes.freezeRows(6);

workbook.recalculate();
const check = await workbook.inspect({
  kind: "table",
  range: `Action Items!A2:H${endRow}`,
  include: "values,formulas",
  tableMaxRows: Math.min(endRow, 30),
  tableMaxCols: 8,
  maxChars: 6000,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
  maxChars: 2000,
});
console.log(check.ndjson);
console.log(errors.ndjson);

await fs.mkdir(path.dirname(previewPath), { recursive: true });
const preview = await workbook.render({ sheetName: "Action Items", autoCrop: "all", scale: 1.2, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await fs.mkdir(path.dirname(outputPath), { recursive: true });
await output.save(outputPath);
