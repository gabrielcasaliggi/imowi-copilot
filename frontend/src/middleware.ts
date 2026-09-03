import { NextResponse, type NextRequest } from "next/server";

import { decideHostRouting, splitHostsFromEnv } from "@/lib/public-hosts";

export function middleware(request: NextRequest) {
  const decision = decideHostRouting(
    request.headers.get("host"),
    request.nextUrl.pathname,
    splitHostsFromEnv(),
  );

  if (decision.type === "redirect") {
    return NextResponse.redirect(decision.url, 308);
  }

  if (decision.type === "rewrite") {
    // Rewrite interno: usamos la URL interna de Next (puede ser http://localhost:3000
    // detrás de nginx) para que el rewrite sea same-process y no cruce al exterior.
    const internalUrl = new URL(
      decision.pathname,
      `http://localhost:${process.env.PORT || 3000}`,
    );
    return NextResponse.rewrite(internalUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|ico|webp|gif|txt|xml|woff2?)$).*)",
  ],
};
