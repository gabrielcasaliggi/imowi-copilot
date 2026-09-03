/**
 * Dos audiencias, dos hosts. Vacío = un solo origen (dev / piloto actual).
 * En prod: consola ibot.ecolan.com · portal soporte.ecolan.com
 */

export type HostConfig = {
  consoleHost: string;
  portalHost: string;
};

export type HostDecision =
  | { type: "next" }
  | { type: "rewrite"; pathname: string }
  | { type: "redirect"; url: string };

const CONSOLE_PREFIXES = [
  "/login",
  "/inbox",
  "/soporte",
  "/tickets",
  "/admin",
  "/conocimiento",
  "/estadisticas",
  "/incidentes",
  "/invite",
  "/change-password",
] as const;

function stripHost(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .replace(/\/.*$/, "")
    .split(":")[0];
}

export function splitHostsFromEnv(
  env: Record<string, string | undefined> = process.env,
): HostConfig {
  return {
    consoleHost: stripHost(env.NEXT_PUBLIC_CONSOLE_HOST || ""),
    portalHost: stripHost(env.NEXT_PUBLIC_PORTAL_HOST || ""),
  };
}

export function hostsAreSplit(cfg: HostConfig): boolean {
  return Boolean(
    cfg.consoleHost && cfg.portalHost && cfg.consoleHost !== cfg.portalHost,
  );
}

export function normalizeHost(hostHeader: string | null | undefined): string {
  return stripHost(hostHeader || "");
}

export function consoleOrigin(cfg: HostConfig): string {
  return cfg.consoleHost ? `https://${cfg.consoleHost}` : "";
}

export function portalOrigin(cfg: HostConfig): string {
  return cfg.portalHost ? `https://${cfg.portalHost}` : "";
}

/** Link al portal público. En un solo host sigue siendo `/portal`. */
export function portalHref(
  path = "/",
  cfg: HostConfig = splitHostsFromEnv(),
): string {
  const clean = path.startsWith("/") ? path : `/${path}`;
  if (!hostsAreSplit(cfg)) {
    if (clean === "/" || clean === "/portal") return "/portal";
    return clean;
  }
  if (clean === "/" || clean === "/portal") return `${portalOrigin(cfg)}/`;
  return `${portalOrigin(cfg)}${clean}`;
}

export function consoleHref(
  path = "/login",
  cfg: HostConfig = splitHostsFromEnv(),
): string {
  const clean = path.startsWith("/") ? path : `/${path}`;
  if (!hostsAreSplit(cfg)) return clean;
  return `${consoleOrigin(cfg)}${clean}`;
}

function isStaticPath(pathname: string): boolean {
  if (pathname.startsWith("/_next")) return true;
  if (pathname.startsWith("/api")) return true;
  if (pathname === "/health" || pathname === "/ready") return true;
  return /\.(?:png|jpe?g|svg|ico|webp|gif|txt|xml|woff2?)$/i.test(pathname);
}

function isConsolePath(pathname: string): boolean {
  return CONSOLE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/**
 * Qué hacer con un request según Host + path.
 * Sin hosts configurados no interviene (dev local).
 */
export function decideHostRouting(
  hostHeader: string | null | undefined,
  pathname: string,
  cfg: HostConfig = splitHostsFromEnv(),
): HostDecision {
  if (!hostsAreSplit(cfg) || isStaticPath(pathname)) return { type: "next" };

  const host = normalizeHost(hostHeader);
  if (!host) return { type: "next" };

  if (host === cfg.portalHost) {
    if (isConsolePath(pathname)) {
      return { type: "redirect", url: consoleHref(pathname, cfg) };
    }
    if (pathname === "/portal" || pathname === "/portal/") {
      return { type: "redirect", url: `${portalOrigin(cfg)}/` };
    }
    if (pathname === "/") {
      return { type: "rewrite", pathname: "/portal" };
    }
    return { type: "next" };
  }

  if (host === cfg.consoleHost) {
    if (pathname === "/portal" || pathname.startsWith("/portal/")) {
      return { type: "redirect", url: `${portalOrigin(cfg)}/` };
    }
    if (pathname === "/privacidad" || pathname.startsWith("/privacidad/")) {
      return { type: "redirect", url: `${portalOrigin(cfg)}/privacidad` };
    }
    return { type: "next" };
  }

  return { type: "next" };
}
