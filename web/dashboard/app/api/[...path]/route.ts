import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (!["pumps", "patients"].includes(path[0])) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  const origin = (process.env.HUB_URL || "http://127.0.0.1:8003").replace(/\/$/, "");
  const url = `${origin}/api/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  try {
    const upstream = await fetch(url, {
      method: request.method,
      headers: { "Content-Type": "application/json", Accept: request.headers.get("accept") || "application/json" },
      body: request.method === "GET" ? undefined : await request.text(),
      cache: "no-store",
      signal: request.signal,
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") || "application/json",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
      },
    });
  } catch {
    return Response.json({ error: "network", detail: "Home hub unavailable" }, { status: 502 });
  }
}
export { proxy as GET, proxy as POST };
