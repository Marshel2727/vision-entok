import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

const methodsWithBody = new Set(["POST", "PUT", "PATCH", "DELETE"]);

async function proxyRequest(request: NextRequest, context: RouteContext) {
  const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  const { path } = await context.params;
  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(`/api/${path.map(encodeURIComponent).join("/")}`, backendUrl);
  targetUrl.search = incomingUrl.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");
  headers.delete("connection");

  const response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body: methodsWithBody.has(request.method) ? await request.arrayBuffer() : undefined,
    redirect: "manual",
    cache: "no-store",
  });

  const responseHeaders = new Headers(response.headers);
  const upstreamHeaders = response.headers as Headers & { getSetCookie?: () => string[] };
  const cookies = upstreamHeaders.getSetCookie?.() ?? [];
  if (cookies.length > 0) {
    responseHeaders.delete("set-cookie");
    for (const cookie of cookies) responseHeaders.append("set-cookie", cookie);
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
export const OPTIONS = proxyRequest;
