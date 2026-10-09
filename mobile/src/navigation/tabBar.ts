import { useSafeAreaInsets } from "react-native-safe-area-context";

import { space } from "../theme/tokens";

/** Alto mínimo de cada pestaña (ícono + etiqueta), sin contar el inset inferior. */
export const TAB_HEIGHT = 52;
const TAB_BAR_BORDER = 1;

/** Inset inferior de la barra: el del sistema, con un mínimo para teléfonos sin barra de gestos. */
export function useTabBarBottomInset(): number {
  return Math.max(useSafeAreaInsets().bottom, space.sm);
}

/** Alto total de la barra de pestañas (borde + padding + pestaña + inset inferior). */
export function useTabBarHeight(): number {
  return TAB_BAR_BORDER + space.sm + TAB_HEIGHT + useTabBarBottomInset();
}

/** paddingBottom para el último elemento de un ScrollView/FlatList de pestaña. */
export function useTabScrollBottomPadding(): number {
  return useTabBarHeight() + space.lg;
}
