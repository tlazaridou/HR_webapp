import { DOMParser, XMLSerializer } from "@xmldom/xmldom";
import ExcelJS from "exceljs";
import JSZip from "jszip";
import { readFile } from "node:fs/promises";
import path from "node:path";

const DATA_DIR = path.join(process.cwd(), "local-data");
const EMPLOYEE_BOOK_PATH = path.join(DATA_DIR, "employees-and-remote-work.xlsx");
const LEAVE_DOC_PATH = path.join(DATA_DIR, "leave-request-template.docx");
const WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
const XML_NS = "http://www.w3.org/XML/1998/namespace";

export const LEAVE_TYPES = ["Κανονική", "Αναρρωτική", "Ειδική"] as const;
export type LeaveType = (typeof LEAVE_TYPES)[number];

export class RequestError extends Error {
  constructor(message: string, public statusCode = 400) {
    super(message);
    this.name = "RequestError";
  }
}

type EmployeeWorkbook = {
  workbook: ExcelJS.Workbook;
  worksheet: ExcelJS.Worksheet;
  nameColumn: number;
  datesColumn: number;
  employees: string[];
};

function fold(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().replace(/\s+/g, " ").toLocaleLowerCase("el-GR");
}

function compact(value: string) {
  return fold(value).replace(/[^a-z0-9\u0370-\u03ff]/gi, "");
}

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number") return String(value).trim();
  if (value instanceof Date) return formatGreekDate(dateToIso(value));
  if (typeof value === "object") {
    const object = value as { text?: unknown; richText?: Array<{ text?: unknown }>; result?: unknown };
    if (Array.isArray(object.richText)) return object.richText.map((part) => String(part.text ?? "")).join("").trim();
    if (typeof object.text === "string") return object.text.trim();
    if (object.result !== undefined) return cellText(object.result);
  }
  return "";
}

function headerKey(value: unknown) {
  return compact(cellText(value));
}

async function loadEmployeeWorkbook(): Promise<EmployeeWorkbook> {
  let bytes: Buffer;
  try {
    bytes = await readFile(EMPLOYEE_BOOK_PATH);
  } catch {
    throw new RequestError("Δεν βρέθηκε το αρχείο ονομάτων στο backend/local-data.", 500);
  }

  const workbook = new ExcelJS.Workbook();
  try {
    await workbook.xlsx.load(bytes);
  } catch {
    throw new RequestError("Το Excel με τα ονόματα δεν είναι έγκυρο αρχείο .xlsx.", 500);
  }

  const worksheet = workbook.worksheets[0];
  if (!worksheet) throw new RequestError("Το Excel δεν περιέχει φύλλο εργασίας.", 500);

  let nameColumn = 0;
  let datesColumn = 0;
  worksheet.getRow(1).eachCell({ includeEmpty: true }, (cell, column) => {
    const key = headerKey(cell.value);
    if (["ονοματεπωνυμο", "oνοματεπωνυμο", "fullname", "employeename", "name"].includes(key)) nameColumn = column;
    if (["remoteworkdates", "τηλεργασιαημερομηνιες"].includes(key)) datesColumn = column;
  });

  if (!nameColumn || !datesColumn) {
    throw new RequestError("Το Excel πρέπει να έχει επικεφαλίδες «Ονοματεπώνυμο» και «remote work dates».", 500);
  }

  const employees: string[] = [];
  const seen = new Set<string>();
  for (let rowNumber = 2; rowNumber <= worksheet.rowCount; rowNumber += 1) {
    const name = cellText(worksheet.getRow(rowNumber).getCell(nameColumn).value);
    const key = fold(name);
    if (name && !seen.has(key)) {
      employees.push(name);
      seen.add(key);
    }
  }

  return { workbook, worksheet, nameColumn, datesColumn, employees };
}

function employeeRow(sheet: ExcelJS.Worksheet, nameColumn: number, employeeName: string) {
  const expected = fold(employeeName);
  for (let rowNumber = 2; rowNumber <= sheet.rowCount; rowNumber += 1) {
    if (fold(cellText(sheet.getRow(rowNumber).getCell(nameColumn).value)) === expected) return rowNumber;
  }
  throw new RequestError("Το επιλεγμένο όνομα δεν υπάρχει πλέον στο Excel. Ανανεώστε τη σελίδα.");
}

export async function getEmployeeNames() {
  const data = await loadEmployeeWorkbook();
  return data.employees;
}

function dateToIso(date: Date) {
  return date.getUTCFullYear().toString().padStart(4, "0") + "-" +
    (date.getUTCMonth() + 1).toString().padStart(2, "0") + "-" +
    date.getUTCDate().toString().padStart(2, "0");
}

export function isIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value + "T00:00:00.000Z");
  return !Number.isNaN(date.getTime()) && dateToIso(date) === value;
}

export function formatGreekDate(value: string) {
  const [year, month, day] = value.split("-");
  return day + "/" + month + "/" + year;
}

function athensTodayIso() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Athens",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date());
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
  return part("year") + "-" + part("month") + "-" + part("day");
}

export function firstAllowedDate() {
  const date = new Date(athensTodayIso() + "T00:00:00.000Z");
  date.setUTCDate(date.getUTCDate() + 1);
  return dateToIso(date);
}

function validateFutureDate(value: unknown, label: string) {
  if (typeof value !== "string" || !isIsoDate(value)) {
    throw new RequestError("Η ημερομηνία «" + label + "» δεν είναι έγκυρη.");
  }
  if (value < firstAllowedDate()) throw new RequestError("Οι ημερομηνίες πρέπει να είναι από αύριο και μετά.");
  return value;
}

export function countWeekdays(startDate: string, endDate: string) {
  let days = 0;
  const current = new Date(startDate + "T00:00:00.000Z");
  const end = new Date(endDate + "T00:00:00.000Z");
  while (current <= end) {
    const weekday = current.getUTCDay();
    if (weekday !== 0 && weekday !== 6) days += 1;
    current.setUTCDate(current.getUTCDate() + 1);
  }
  return days;
}

function directChildren(element: Element, localName: string) {
  const result: Element[] = [];
  for (let node = element.firstChild; node; node = node.nextSibling) {
    if (node.nodeType === 1 && (node as Element).localName === localName) result.push(node as Element);
  }
  return result;
}

function wordCellText(cell: Element) {
  const textNodes = cell.getElementsByTagNameNS(WORD_NS, "t");
  let value = "";
  for (let index = 0; index < textNodes.length; index += 1) value += textNodes.item(index)?.textContent ?? "";
  return value;
}

function setWordCellText(document: Document, cell: Element, value: string) {
  const textNodes = cell.getElementsByTagNameNS(WORD_NS, "t");
  if (textNodes.length > 0) {
    const first = textNodes.item(0);
    if (first) {
      first.textContent = value;
      if (first.parentNode?.nodeType === 1) (first.parentNode as Element).setAttributeNS(XML_NS, "xml:space", "preserve");
    }
    for (let index = 1; index < textNodes.length; index += 1) {
      const textNode = textNodes.item(index);
      if (textNode) textNode.textContent = "";
    }
    return;
  }

  let paragraph: Element | null = cell.getElementsByTagNameNS(WORD_NS, "p").item(0);
  if (!paragraph) {
    paragraph = document.createElementNS(WORD_NS, "w:p");
    cell.appendChild(paragraph);
  }
  const run = document.createElementNS(WORD_NS, "w:r");
  const text = document.createElementNS(WORD_NS, "w:t");
  text.textContent = value;
  text.setAttributeNS(XML_NS, "xml:space", "preserve");
  run.appendChild(text);
  paragraph.appendChild(run);
}

function replaceWordValue(document: Document, label: string, value: string) {
  const rows = document.getElementsByTagNameNS(WORD_NS, "tr");
  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    const row = rows.item(rowIndex);
    if (!row) continue;
    const cells = directChildren(row, "tc");
    for (let cellIndex = 0; cellIndex < cells.length - 1; cellIndex += 1) {
      if (compact(wordCellText(cells[cellIndex]).replace(/:$/, "")) === label) {
        setWordCellText(document, cells[cellIndex + 1], value);
        return true;
      }
    }
  }
  return false;
}

export async function createLeaveDocument(input: {
  employeeName: string;
  startDate: string;
  endDate: string;
  leaveType: string;
}) {
  const book = await loadEmployeeWorkbook();
  if (!book.employees.some((name) => fold(name) === fold(input.employeeName))) {
    throw new RequestError("Το όνομα δεν υπάρχει στη λίστα εργαζομένων του Excel.");
  }

  const startDate = validateFutureDate(input.startDate, "Από");
  const endDate = validateFutureDate(input.endDate, "Έως");
  if (startDate > endDate) throw new RequestError("Η ημερομηνία έναρξης πρέπει να είναι πριν ή ίση με τη λήξη.");
  if (!LEAVE_TYPES.includes(input.leaveType as LeaveType)) throw new RequestError("Επιλέξτε έγκυρο τύπο άδειας.");
  const days = countWeekdays(startDate, endDate);
  if (days === 0) throw new RequestError("Το διάστημα δεν περιέχει εργάσιμη ημέρα.");

  let template: Buffer;
  try {
    template = await readFile(LEAVE_DOC_PATH);
  } catch {
    throw new RequestError("Δεν βρέθηκε το πρότυπο αίτησης άδειας στο backend/local-data.", 500);
  }

  const archive = await JSZip.loadAsync(template);
  const documentXml = archive.file("word/document.xml");
  if (!documentXml) throw new RequestError("Το πρότυπο Word δεν περιέχει το κύριο έγγραφο.", 500);
  const xml = (await documentXml.async("string")).replace(/^\uFEFF/, "").trimStart();
  const document = new DOMParser().parseFromString(xml, "application/xml");
  const fields = [
    { label: "ονοματεπωνυμο", value: input.employeeName },
    { label: "ημερομινιαδηλωσης", value: formatGreekDate(athensTodayIso()) },
    { label: "ημερεςαδειας", value: String(days) },
    { label: "απο", value: formatGreekDate(startDate) },
    { label: "εως", value: formatGreekDate(endDate) },
    { label: "τυποςαδειας", value: input.leaveType }
  ];

  for (const field of fields) {
    if (!replaceWordValue(document, field.label, field.value)) {
      throw new RequestError("Δεν βρέθηκε το πεδίο «" + field.label + "» στο πρότυπο Word.", 500);
    }
  }

  archive.file("word/document.xml", new XMLSerializer().serializeToString(document));
  const output = await archive.generateAsync({ type: "nodebuffer" });
  return new Uint8Array(output);
}

function dateTokens(value: unknown): string[] {
  if (value instanceof Date) return [dateToIso(value)];
  const text = cellText(value);
  return text.split(/[,\n;]+/).map((part) => {
    const token = part.trim();
    if (isIsoDate(token)) return token;
    const match = token.match(/^(\d{1,2})[/. -](\d{1,2})[/. -](\d{4})$/);
    if (match) {
      const iso = match[3] + "-" + match[2].padStart(2, "0") + "-" + match[1].padStart(2, "0");
      if (isIsoDate(iso)) return iso;
    }
    return token;
  }).filter(Boolean);
}

export async function createRemoteWorkWorkbook(employeeName: string, requestedDates: string[]) {
  const data = await loadEmployeeWorkbook();
  if (!data.employees.some((name) => fold(name) === fold(employeeName))) {
    throw new RequestError("Το όνομα δεν υπάρχει στη λίστα εργαζομένων του Excel.");
  }

  const dates = [...new Set(requestedDates.map((date) => validateFutureDate(date, "τηλεργασία")))].sort();
  if (dates.length === 0) throw new RequestError("Επιλέξτε τουλάχιστον μία ημερομηνία τηλεργασίας.");
  for (const date of dates) {
    const weekday = new Date(date + "T00:00:00.000Z").getUTCDay();
    if (weekday === 0 || weekday === 6) throw new RequestError("Η τηλεργασία μπορεί να προγραμματιστεί μόνο Δευτέρα έως Παρασκευή.");
  }

  const rowNumber = employeeRow(data.worksheet, data.nameColumn, employeeName);
  const dateCell = data.worksheet.getRow(rowNumber).getCell(data.datesColumn);
  const merged = dateTokens(dateCell.value);
  for (const date of dates) if (!merged.includes(date)) merged.push(date);
  merged.sort();
  dateCell.value = merged.map((date) => isIsoDate(date) ? formatGreekDate(date) : date).join(", ");
  dateCell.alignment = { ...dateCell.alignment, wrapText: true };

  const output = await data.workbook.xlsx.writeBuffer();
  return new Uint8Array(output);
}

