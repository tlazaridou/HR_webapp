import { NextResponse } from "next/server";
import { getEmployeeNames } from "../../../../lib/request-files";

export const runtime = "nodejs";

export async function GET() {
  try {
    const employees = await getEmployeeNames();
    return NextResponse.json({
      employees,
      message: employees.length
        ? null
        : "Το Excel δεν έχει ονόματα ακόμη. Πρόσθεσέ τα στη στήλη «Ονοματεπώνυμο», από τη γραμμή 2."
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Δεν ήταν δυνατή η ανάγνωση του Excel.";
    return NextResponse.json({ employees: [], error: message }, { status: 500 });
  }
}
