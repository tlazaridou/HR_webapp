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
import time
import zipfile
from datetime import date, datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape, unescape

ROOT = os.path.dirname(os.path.abspath(__file__))
REMOTE_BOOK = os.path.join(ROOT, "local-data", "remote-work-dates.xlsx")
LEAVE_BOOK = os.path.join(ROOT, "local-data", "leave-requests.xlsx")
LEAVE_HEADERS = ["Full Name", "From", "To", "Leave Type", "Working Days", "Submitted"]
LEAVE_TYPES = ["Κανονική", "Αναρρωτική", "Ειδική"]
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


def load_book(path=None):
    """Return (sheet xml, shared strings) of a workbook (the remote-work one by default)."""
    path = path or REMOTE_BOOK
    if not os.path.exists(path):
        raise RequestError("The Excel file %s was not found in local-data." % os.path.basename(path), 500)
    with zipfile.ZipFile(path) as book:
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

    save_sheet(sheet)
    return len(new_dates)


def save_sheet(sheet, path=None):
    """Fix the sheet dimension and write the sheet back into the workbook."""
    path = path or REMOTE_BOOK
    last_column = max(column_index(letters) for letters in re.findall(r'<c r="([A-Z]+)\d+"', sheet))
    last_row = max(int(number) for number in re.findall(r'<row r="(\d+)"', sheet))
    sheet = re.sub(r'<dimension ref="[^"]*"/>', '<dimension ref="A1:%s%d"/>' % (column_letter(last_column), last_row), sheet, count=1)

    handle, temp_path = tempfile.mkstemp(suffix=".xlsx", dir=os.path.dirname(path))
    os.close(handle)
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = sheet.encode("utf-8") if item.filename == SHEET else source.read(item.filename)
            target.writestr(item, data)
    try:
        os.replace(temp_path, path)
    except PermissionError:
        os.remove(temp_path)
        raise RequestError("The Excel file is open in another program. Close it and try again.", 409)


# ---- Leave requests (leave-requests.xlsx) ----

def parse_display_date(text):
    return datetime.strptime(text, "%d/%m/%Y").date()


def weekdays_between(start, end):
    """The Monday-Friday dates from start to end (both included)."""
    days = set()
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.add(current)
        current += timedelta(days=1)
    return days


def create_leave_book():
    """Create an empty leave-requests.xlsx (header row only) the first time it is needed."""
    os.makedirs(os.path.dirname(LEAVE_BOOK), exist_ok=True)
    header = "".join(text_cell("%s1" % column_letter(index + 1), title) for index, title in enumerate(LEAVE_HEADERS))
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Leave Requests" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        SHEET: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:F1"/><cols><col min="1" max="1" width="28" customWidth="1"/><col min="2" max="3" width="14" customWidth="1"/><col min="4" max="4" width="16" customWidth="1"/><col min="5" max="6" width="15" customWidth="1"/></cols><sheetData><row r="1">' + header + '</row></sheetData></worksheet>',
    }
    with zipfile.ZipFile(LEAVE_BOOK, "w", zipfile.ZIP_DEFLATED) as book:
        for name, content in files.items():
            book.writestr(name, content)


def read_leave_table():
    """The saved leaves as lists of texts (header excluded)."""
    if not os.path.exists(LEAVE_BOOK):
        create_leave_book()
    sheet, shared = load_book(LEAVE_BOOK)
    table = []
    for number, content in re.findall(r'<row r="(\d+)"[^>]*>(.*?)</row>', sheet, re.S):
        if number == "1":
            continue
        cells = row_cells(content, shared)
        table.append([cells.get(index, "") for index in range(1, len(LEAVE_HEADERS) + 1)])
    return table


def write_leave_table(table):
    """Replace the data rows of leave-requests.xlsx (the header row stays)."""
    sheet, _ = load_book(LEAVE_BOOK)
    rows_xml = ""
    for offset, values in enumerate(table):
        number = offset + 2
        rows_xml += '<row r="%d">%s</row>' % (number, "".join(
            text_cell("%s%d" % (column_letter(index + 1), number), value) for index, value in enumerate(values)))
    header = re.search(r'<row r="1"[^>]*>.*?</row>', sheet, re.S)
    sheet = re.sub(r"<sheetData>.*</sheetData>", lambda match: "<sheetData>" + (header.group(0) if header else "") + rows_xml + "</sheetData>", sheet, count=1, flags=re.S)
    save_sheet(sheet, LEAVE_BOOK)


def read_leave_rows():
    """The saved leaves as dicts, earliest start date first."""
    rows = [dict(zip(("name", "from", "to", "type", "days", "submitted"), values)) for values in read_leave_table()]

    def sort_key(row):
        try:
            return (parse_display_date(row["from"]), row["name"].casefold())
        except ValueError:
            return (date.max, row["name"].casefold())

    return sorted(rows, key=sort_key)


def leaves_of(name):
    """[(start, end)] of the saved leaves of one employee."""
    leaves = []
    for values in read_leave_table():
        if same_name(values[0], name):
            try:
                leaves.append((parse_display_date(values[1]), parse_display_date(values[2])))
            except ValueError:
                pass
    return leaves


def remote_dates_of(name):
    """The remote-work dates of one employee, as date objects."""
    found = []
    for entry in read_rows():
        if same_name(entry["name"], name):
            for text in entry["dates"]:
                try:
                    found.append(parse_display_date(text))
                except ValueError:
                    pass
    return found


def show(day):
    return day.strftime("%d/%m/%Y")


def check_leave_overlaps(name, start, end):
    requested = weekdays_between(start, end)
    for other_start, other_end in leaves_of(name):
        if requested & weekdays_between(other_start, other_end):
            raise RequestError("%s already has a leave from %s to %s that overlaps with these dates." % (name, show(other_start), show(other_end)), 409)
    for day in sorted(remote_dates_of(name)):
        if day in requested:
            raise RequestError("%s has remote work on %s, which falls inside the requested leave." % (name, show(day)), 409)


def check_remote_conflicts(name, dates):
    for other_start, other_end in leaves_of(name):
        taken = weekdays_between(other_start, other_end)
        for day in dates:
            if day in taken:
                raise RequestError("%s is on leave from %s to %s, which includes %s." % (name, show(other_start), show(other_end), show(day)), 409)


def validate_leave(payload):
    name = re.sub(r"\s+", " ", str(payload.get("employeeName", ""))).strip()
    if not name or len(name) > 100:
        raise RequestError("Select an employee.")
    try:
        start = datetime.strptime(str(payload.get("startDate", "")), "%Y-%m-%d").date()
        end = datetime.strptime(str(payload.get("endDate", "")), "%Y-%m-%d").date()
    except ValueError:
        raise RequestError("The leave dates are not valid.")
    if start < date.today() + timedelta(days=1):
        raise RequestError("Dates must be from tomorrow onwards.")
    if end < start:
        raise RequestError("The start date must be before the end date.")
    leave_type = str(payload.get("leaveType", ""))
    if leave_type not in LEAVE_TYPES:
        raise RequestError("Select a valid leave type.")
    if not weekdays_between(start, end):
        raise RequestError("The selected period has no working days.")
    return name, start, end, leave_type


def save_leave(name, start, end, leave_type):
    """Check for overlaps, then add the leave as a new row. Returns the number of working days."""
    check_leave_overlaps(name, start, end)
    days = len(weekdays_between(start, end))
    table = read_leave_table()
    table.append([name, show(start), show(end), leave_type, str(days), show(date.today())])
    write_leave_table(table)
    return days


def purge_leaves():
    """Remove the leaves that have already ended."""
    if not os.path.exists(LEAVE_BOOK):
        return 0
    table = read_leave_table()
    today = date.today()
    kept = []
    for values in table:
        try:
            ended = parse_display_date(values[2]) < today
        except ValueError:
            ended = False
        if not ended:
            kept.append(values)
    if len(kept) == len(table):
        return 0
    write_leave_table(kept)
    return 1


def purge_expired():
    """Delete the dates that are already in the past (and the rows left without dates)."""
    sheet, shared = load_book()
    today = date.today()
    kept_rows = []
    changed = False
    for number, content in re.findall(r'<row r="(\d+)"[^>]*>(.*?)</row>', sheet, re.S):
        if number == "1":
            continue
        cells = row_cells(content, shared)
        name = cells.get(1, "")
        dates = [text for index, text in sorted(cells.items()) if index > 1 and text]
        upcoming = []
        for text in dates:
            try:
                expired = datetime.strptime(text, "%d/%m/%Y").date() < today
            except ValueError:
                expired = False  # not a date: leave it alone
            if not expired:
                upcoming.append(text)
        if len(upcoming) != len(dates) or not (name or upcoming):
            changed = True
        if name and upcoming:
            kept_rows.append((name, sort_dates(upcoming)))
        elif not name and upcoming:
            kept_rows.append(("", sort_dates(upcoming)))
        elif name:
            changed = True
    if not changed:
        return 0

    rows_xml = ""
    for offset, (name, dates) in enumerate(kept_rows):
        number = offset + 2
        rows_xml += '<row r="%d">%s%s</row>' % (
            number,
            text_cell("A%d" % number, name),
            "".join(text_cell("%s%d" % (column_letter(2 + position), number), day) for position, day in enumerate(dates)),
        )
    header = re.search(r'<row r="1"[^>]*>.*?</row>', sheet, re.S)
    sheet = re.sub(r"<sheetData>.*</sheetData>", lambda match: "<sheetData>" + (header.group(0) if header else "") + rows_xml + "</sheetData>", sheet, count=1, flags=re.S)
    save_sheet(sheet)
    return 1


def purge_quietly():
    """Run the clean-up; if the file is busy it is simply retried on the next round."""
    try:
        with write_lock:
            purge_expired()
            purge_leaves()
    except Exception as error:
        print("Clean-up skipped:", error)


def purge_forever(interval_seconds=600):
    while True:
        purge_quietly()
        time.sleep(interval_seconds)


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
                purge_quietly()
                with write_lock:
                    rows = read_rows()
                self.send_json(200, {"rows": rows})
            except RequestError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception:
                self.send_json(500, {"error": "Could not read the saved requests."})
            return
        if self.path == "/api/leave-requests":
            try:
                purge_quietly()
                with write_lock:
                    rows = read_leave_rows()
                self.send_json(200, {"rows": rows})
            except RequestError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception:
                self.send_json(500, {"error": "Could not read the saved leave requests."})
            return
        if self.path in ("/api/remote-work/download", "/api/leave-requests/download"):
            purge_quietly()
            remote = self.path.startswith("/api/remote-work")
            try:
                with write_lock:
                    if not remote and not os.path.exists(LEAVE_BOOK):
                        create_leave_book()
                    with open(REMOTE_BOOK if remote else LEAVE_BOOK, "rb") as book:
                        data = book.read()
            except OSError:
                self.send_json(500, {"error": "Could not read the Excel file."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % ("remote-work-dates.xlsx" if remote else "leave-requests.xlsx"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def handle_leave_request(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 100_000:
                raise RequestError("The request is too large.")
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                raise RequestError("The request is not valid.")
            name, start, end, leave_type = validate_leave(payload)
            with write_lock:
                days = save_leave(name, start, end, leave_type)
            self.send_json(200, {"saved": True, "days": days})
        except RequestError as error:
            self.send_json(error.status, {"error": str(error)})
        except Exception:
            self.send_json(500, {"error": "Could not save the leave request."})

    def do_POST(self):
        if self.path == "/api/leave-requests":
            self.handle_leave_request()
            return
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
                check_remote_conflicts(name, dates)
                saved = append_request(name, dates)
            self.send_json(200, {"saved": saved})
        except RequestError as error:
            self.send_json(error.status, {"error": str(error)})
        except Exception:
            self.send_json(500, {"error": "Could not save the request."})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5500
    threading.Thread(target=purge_forever, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=ROOT))
    print("Serving the front end at http://localhost:%d" % port)
    server.serve_forever()
