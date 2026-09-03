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
    const url = request.nextUrl.clone();
    url.pathname = decision.pathname;
    return NextResponse.rewrite(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|ico|webp|gif|txt|xml|woff2?)$).*)",
  ],
};
