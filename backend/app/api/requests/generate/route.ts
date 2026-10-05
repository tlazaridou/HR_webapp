import { NextRequest, NextResponse } from "next/server";
import {
  createLeaveDocument,
  createRemoteWorkWorkbook,
  RequestError
} from "../../../../lib/request-files";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  let body: Record<string, unknown>;
  try {
    body = await request.json() as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Τα στοιχεία της αίτησης δεν ήταν έγκυρα." }, { status: 400 });
  }

  try {
    if (typeof body.employeeName !== "string" || !body.employeeName.trim()) {
      throw new RequestError("Επίλεξε εργαζόμενο.");
    }

    if (body.kind === "leave") {
      if (typeof body.startDate !== "string" || typeof body.endDate !== "string" || typeof body.leaveType !== "string") {
        throw new RequestError("Συμπλήρωσε ημερομηνίες και τύπο άδειας.");
      }
      const file = await createLeaveDocument({
        employeeName: body.employeeName.trim(),
        startDate: body.startDate,
        endDate: body.endDate,
        leaveType: body.leaveType
      });
      return new NextResponse(file, {
        headers: {
          "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          "content-disposition": "attachment; filename=\"leave-request.docx\"",
          "cache-control": "no-store"
        }
      });
    }

    if (body.kind === "remote_work") {
      if (!Array.isArray(body.dates) || !body.dates.every((date) => typeof date === "string")) {
        throw new RequestError("Επίλεξε τουλάχιστον μία ημερομηνία τηλεργασίας.");
      }
      const file = await createRemoteWorkWorkbook(body.employeeName.trim(), body.dates as string[]);
      return new NextResponse(file, {
        headers: {
          "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "content-disposition": "attachment; filename=\"remote-work.xlsx\"",
          "cache-control": "no-store"
        }
      });
    }

    throw new RequestError("Επίλεξε άδεια ή τηλεργασία.");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Δεν ήταν δυνατή η δημιουργία του αρχείου.";
    const status = error instanceof RequestError ? error.statusCode : 500;
    return NextResponse.json({ error: message }, { status });
  }
}
