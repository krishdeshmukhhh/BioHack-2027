import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (!["pumps", "patients"].includes(path[0])) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  // No default: a forgotten HUB_URL must fail loudly, never fall back to the mock and
  // show fake pump data as if it were the real pump (S5, S8).
  if (!process.env.HUB_URL) {
    return Response.json(
      { error: "hub_url_not_set", detail: "Set HUB_URL to the hub, e.g. http://127.0.0.1:8000" },
      { status: 503 },
    );
  }
  const origin = process.env.HUB_URL.replace(/\/$/, "");
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
