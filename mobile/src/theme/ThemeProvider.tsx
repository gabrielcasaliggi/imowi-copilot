import * as SecureStore from "expo-secure-store";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useColorScheme } from "react-native";

import {
  fontSize,
  palette,
  radius,
  size,
  space,
  type ColorScheme,
  type ThemeColors,
} from "./tokens";

/**
 * H-APP-1: el selector de tema queda apagado hasta migrar las 5 pantallas.
 * Con `false` la app se ve siempre en oscuro aunque haya una preferencia guardada.
 * La pieza 9 lo pasa a `true` junto con `userInterfaceStyle: "automatic"`.
 */
export const THEME_SELECTOR_ENABLED = false;

export type ThemePreference = "system" | "light" | "dark";

const PREF_KEY = "theme_pref";
const PREFS: ThemePreference[] = ["system", "light", "dark"];

export type Theme = {
  scheme: ColorScheme;
  colors: ThemeColors;
  fontSize: typeof fontSize;
  radius: typeof radius;
  space: typeof space;
  size: typeof size;
};

type ThemeContextValue = {
  theme: Theme;
  preference: ThemePreference;
  setPreference: (pref: ThemePreference) => void;
  selectorEnabled: boolean;
};

function buildTheme(scheme: ColorScheme): Theme {
  return { scheme, colors: palette[scheme], fontSize, radius, space, size };
}

const THEMES: Record<ColorScheme, Theme> = {
  light: buildTheme("light"),
  dark: buildTheme("dark"),
};

export function resolveScheme(
  preference: ThemePreference,
  system: ColorScheme | null | undefined,
  selectorEnabled: boolean,
): ColorScheme {
  if (!selectorEnabled) return "dark";
  if (preference === "system") return system === "light" ? "light" : "dark";
  return preference;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: THEMES.dark,
  preference: "system",
  setPreference: () => {},
  selectorEnabled: THEME_SELECTOR_ENABLED,
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const [preference, setPreferenceState] = useState<ThemePreference>("system");

  useEffect(() => {
    let alive = true;
    SecureStore.getItemAsync(PREF_KEY)
      .then((raw) => {
        if (alive && raw && (PREFS as string[]).includes(raw)) {
          setPreferenceState(raw as ThemePreference);
        }
      })
      .catch(() => {
        /* sin preferencia guardada: queda "system" */
      });
    return () => {
      alive = false;
    };
  }, []);

  const setPreference = useCallback((pref: ThemePreference) => {
    setPreferenceState(pref);
    SecureStore.setItemAsync(PREF_KEY, pref).catch(() => {
      /* la preferencia vale para esta sesión aunque no se pueda guardar */
    });
  }, []);

  const scheme = resolveScheme(preference, system, THEME_SELECTOR_ENABLED);
  const value = useMemo<ThemeContextValue>(
    () => ({
      theme: THEMES[scheme],
      preference,
      setPreference,
      selectorEnabled: THEME_SELECTOR_ENABLED,
    }),
    [scheme, preference, setPreference],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  return useContext(ThemeContext).theme;
}

export function useThemePreference() {
  const { preference, setPreference, selectorEnabled } = useContext(ThemeContext);
  return { preference, setPreference, selectorEnabled };
}

/**
 * Estilos que dependen del tema; se recalculan solo cuando cambia el modo.
 * `factory` debe ser una función a nivel de módulo (p. ej. `makeStyles`), no una inline.
 */
export function useThemedStyles<T>(factory: (theme: Theme) => T): T {
  const theme = useTheme();
  return useMemo(() => factory(theme), [theme]);
}
