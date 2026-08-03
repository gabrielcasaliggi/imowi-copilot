/**
 * Branding del asistente abonado (N1).
 * Distinct from Copilot NOC (consola operadores).
 */

export type Branding = {
  botDisplayName: string;
  botDisplayNameShort: string;
  orgHint: string;
};

const DEFAULTS: Branding = {
  botDisplayName: process.env.NEXT_PUBLIC_BOT_DISPLAY_NAME?.trim() || "Eco",
  botDisplayNameShort: (
    process.env.NEXT_PUBLIC_BOT_DISPLAY_NAME_SHORT?.trim() ||
    process.env.NEXT_PUBLIC_BOT_DISPLAY_NAME?.trim() ||
    "Eco"
  ).toUpperCase(),
  orgHint: "Cooperativa Batán",
};

let cached: Branding = { ...DEFAULTS };

export function getBranding(): Branding {
  return cached;
}

/** Label de badge/filtro para estado canal `bot`. */
export function botEstadoLabel(): string {
  return `${cached.botDisplayName} (N1)`;
}

export function applyBranding( partial: {
  bot_display_name?: string;
  bot_display_name_short?: string;
  org_hint?: string;
}): Branding {
  cached = {
    botDisplayName: partial.bot_display_name?.trim() || cached.botDisplayName,
    botDisplayNameShort: (
      partial.bot_display_name_short?.trim() ||
      partial.bot_display_name?.trim() ||
      cached.botDisplayNameShort
    ).toUpperCase(),
    orgHint: partial.org_hint?.trim() || cached.orgHint,
  };
  return cached;
}

export async function hydrateBranding(apiBase?: string): Promise<Branding> {
  const base = (apiBase || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(
    /\/$/,
    "",
  );
  try {
    const res = await fetch(`${base}/api/v1/public/branding`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return cached;
    const data = (await res.json()) as {
      bot_display_name?: string;
      bot_display_name_short?: string;
      org_hint?: string;
    };
    return applyBranding(data);
  } catch {
    return cached;
  }
}
