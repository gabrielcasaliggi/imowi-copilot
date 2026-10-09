import Ionicons from "@expo/vector-icons/Ionicons";
import type { ComponentProps } from "react";

import { useTheme } from "../theme/ThemeProvider";
import type { AppTab } from "../types";

type IconName = ComponentProps<typeof Ionicons>["name"];

const ICON = 22;

const ICONS: Record<AppTab, { on: IconName; off: IconName }> = {
  home: { on: "home", off: "home-outline" },
  eko: { on: "chatbubble-ellipses", off: "chatbubble-ellipses-outline" },
  activity: { on: "receipt", off: "receipt-outline" },
  account: { on: "person-circle", off: "person-circle-outline" },
};

export function TabGlyph({
  tab,
  active,
}: {
  tab: AppTab;
  active: boolean;
}) {
  const { colors } = useTheme();
  return (
    <Ionicons
      name={active ? ICONS[tab].on : ICONS[tab].off}
      size={ICON}
      color={active ? colors.primary : colors.muted}
      allowFontScaling={false}
      accessible={false}
      importantForAccessibility="no"
    />
  );
}
