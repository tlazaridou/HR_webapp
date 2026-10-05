import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";

export async function GET() {
  const html = await readFile(path.join(process.cwd(), "public", "index.html"), "utf8");
  return new NextResponse(html, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}
