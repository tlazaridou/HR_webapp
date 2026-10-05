import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  let payload: { message?: unknown; sessionId?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "Το μήνυμα δεν ήταν έγκυρο." }, { status: 400 });
  }

  if (typeof payload.message !== "string" || !payload.message.trim()) {
    return NextResponse.json({ error: "Γράψε πρώτα ένα μήνυμα." }, { status: 400 });
  }

  const backendUrl = process.env.BACKEND_API_URL ?? "http://localhost:4000";
  try {
    const upstream = await fetch(new URL("/api/v1/chat/message", backendUrl), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        message: payload.message.trim(),
        sessionId: typeof payload.sessionId === "string" ? payload.sessionId : null
      }),
      cache: "no-store"
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" }
    });
  } catch {
    return NextResponse.json(
      { error: "Δεν υπάρχει σύνδεση με το HR backend. Έλεγξε ότι εκτελείται και δοκίμασε ξανά." },
      { status: 503 }
    );
  }
}
