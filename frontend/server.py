"""Local server for the HR web app front end.

Serves the files in this folder and saves submitted remote-work requests
into local-data/remote-work-dates.xlsx. Each employee has one row: the full
name in column A and every requested date in the columns next to it (B, C, D...).
Uses only the Python standard library.

    python frontend/server.py [port]
"""
import json
import os
import re
import sys
import tempfile
import threading
import zipfile
from datetime import date, datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape, unescape

ROOT = os.path.dirname(os.path.abspath(__file__))
REMOTE_BOOK = os.path.join(ROOT, "local-data", "remote-work-dates.xlsx")
SHEET = "xl/worksheets/sheet1.xml"
write_lock = threading.Lock()


class RequestError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def validate(payload):
    name = re.sub(r"\s+", " ", str(payload.get("employeeName", ""))).strip()
    if not name or len(name) > 100:
        raise RequestError("Select an employee.")
    raw_dates = payload.get("dates")
    if not isinstance(raw_dates, list) or not raw_dates:
        raise RequestError("Select at least one remote-work date.")
    earliest = date.today() + timedelta(days=1)
    dates = set()
    for value in raw_dates:
        try:
            day = datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            raise RequestError("One of the dates is not valid.")
        if day < earliest:
            raise RequestError("Dates must be from tomorrow onwards.")
        if day.weekday() >= 5:
            raise RequestError("Remote work can only be requested for weekdays.")
        dates.add(day)
    return name, sorted(dates)


def column_letter(index):
    """1 -> A, 2 -> B, 27 -> AA"""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def column_index(letters):
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index


def sort_dates(texts):
    """Sort dd/mm/yyyy texts chronologically; anything that is not a date goes last."""
    def key(text):
        try:
            return (0, datetime.strptime(text, "%d/%m/%Y"), text)
        except ValueError:
            return (1, datetime.max, text)
    return sorted(texts, key=key)


def same_name(first, second):
    return re.sub(r"\s+", " ", first).strip().casefold() == re.sub(r"\s+", " ", second).strip().casefold()


def text_cell(ref, value):
    return '<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, escape(value))


def load_book():
    """Return (sheet xml, shared strings) of the remote-work workbook."""
    if not os.path.exists(REMOTE_BOOK):
        raise RequestError("The remote-work Excel file was not found in local-data.", 500)
    with zipfile.ZipFile(REMOTE_BOOK) as book:
        sheet = book.read(SHEET).decode("utf-8")
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            xml = book.read("xl/sharedStrings.xml").decode("utf-8")
            for item in re.findall(r"<si>(.*?)</si>", xml, re.S):
                shared.append(unescape("".join(re.findall(r"<t[^>]*>([^<]*)</t>", item))))
    return sheet, shared


def cell_text(attributes, body, shared):
    kind = re.search(r'\bt="(\w+)"', attributes)
    body = body or ""
    if kind and kind.group(1) == "s":
        index = re.search(r"<v>(\d+)</v>", body)
        return shared[int(index.group(1))].strip() if index and int(index.group(1)) < len(shared) else ""
    if kind and kind.group(1) == "inlineStr":
        return unescape("".join(re.findall(r"<t[^>]*>([^<]*)</t>", body))).strip()
    value = re.search(r"<v>([^<]*)</v>", body)
    return unescape(value.group(1)).strip() if value else ""


def row_cells(row_xml, shared):
    """{column index: text} for the cells of one row."""
    cells = {}
    for cell in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', row_xml, re.S):
        cells[column_index(cell.group(1))] = cell_text(cell.group(2), cell.group(3), shared)
    return cells


def read_rows():
    """Return the saved requests as [{"name": ..., "dates": [...]}], sorted by name."""
    sheet, shared = load_book()
    rows = []
    for number, content in re.findall(r'<row r="(\d+)"[^>]*>(.*?)</row>', sheet, re.S):
        if number == "1":
            continue
        cells = row_cells(content, shared)
        name = cells.get(1, "")
        dates = sort_dates([cells[index] for index in sorted(cells) if index > 1 and cells[index]])
        if name:
            rows.append({"name": name, "dates": dates})
    return sorted(rows, key=lambda entry: entry["name"].casefold())


def append_request(name, dates):
    """Add the dates to the employee's row, or create the row if the name is new."""
    sheet, shared = load_book()
    wanted = [day.strftime("%d/%m/%Y") for day in dates]

    existing = None
    last_row = 0
    for match in re.finditer(r'<row r="(\d+)"([^>]*)>(.*?)</row>', sheet, re.S):
        last_row = max(last_row, int(match.group(1)))
        if match.group(1) != "1" and same_name(row_cells(match.group(3), shared).get(1, ""), name):
            existing = match

    if existing:
        cells = row_cells(existing.group(3), shared)
        row_number = existing.group(1)
        old_dates = [text for index, text in sorted(cells.items()) if index > 1 and text]
        new_dates = [day for day in wanted if day not in old_dates]
        if not new_dates:
            return 0
        # Keep the name cell as it is and rewrite the date cells in chronological order
        name_cell = re.search(r'<c r="A%s"[^>]*?(?:/>|>.*?</c>)' % row_number, existing.group(3), re.S)
        all_dates = sort_dates(old_dates + new_dates)
        dates_xml = "".join(text_cell("%s%s" % (column_letter(2 + offset), row_number), day) for offset, day in enumerate(all_dates))
        attributes = re.sub(r'\sspans="[^"]*"', "", existing.group(2))
        replacement = '<row r="%s"%s>%s%s</row>' % (row_number, attributes, name_cell.group(0) if name_cell else text_cell("A" + row_number, name), dates_xml)
        sheet = sheet[:existing.start()] + replacement + sheet[existing.end():]
    else:
        row_number = last_row + 1
        added = text_cell("A%d" % row_number, name) + "".join(
            text_cell("%s%d" % (column_letter(2 + offset), row_number), day) for offset, day in enumerate(wanted))
        sheet = sheet.replace("</sheetData>", '<row r="%d">%s</row></sheetData>' % (row_number, added), 1)
        new_dates = wanted

    last_column = max(column_index(letters) for letters in re.findall(r'<c r="([A-Z]+)\d+"', sheet))
    last_row = max(int(number) for number in re.findall(r'<row r="(\d+)"', sheet))
    sheet = re.sub(r'<dimension ref="[^"]*"/>', '<dimension ref="A1:%s%d"/>' % (column_letter(last_column), last_row), sheet, count=1)

    handle, temp_path = tempfile.mkstemp(suffix=".xlsx", dir=os.path.dirname(REMOTE_BOOK))
    os.close(handle)
    with zipfile.ZipFile(REMOTE_BOOK) as source, zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = sheet.encode("utf-8") if item.filename == SHEET else source.read(item.filename)
            target.writestr(item, data)
    try:
        os.replace(temp_path, REMOTE_BOOK)
    except PermissionError:
        os.remove(temp_path)
        raise RequestError("The Excel file is open in another program. Close it and try again.", 409)
    return len(new_dates)


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, status, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/remote-work":
            try:
                with write_lock:
                    rows = read_rows()
                self.send_json(200, {"rows": rows})
            except RequestError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception:
                self.send_json(500, {"error": "Could not read the saved requests."})
            return
        if self.path == "/api/remote-work/download":
            try:
                with write_lock, open(REMOTE_BOOK, "rb") as book:
                    data = book.read()
            except OSError:
                self.send_json(500, {"error": "Could not read the Excel file."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", 'attachment; filename="remote-work-dates.xlsx"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def do_POST(self):
        if self.path != "/api/remote-work":
            self.send_json(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 100_000:
                raise RequestError("The request is too large.")
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                raise RequestError("The request is not valid.")
            name, dates = validate(payload)
            with write_lock:
                saved = append_request(name, dates)
            self.send_json(200, {"saved": saved})
        except RequestError as error:
            self.send_json(error.status, {"error": str(error)})
        except Exception:
            self.send_json(500, {"error": "Could not save the request."})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5500
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=ROOT))
    print("Serving the front end at http://localhost:%d" % port)
    server.serve_forever()
