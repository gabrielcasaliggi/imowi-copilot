import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, radius, sizes, spacing } from "../theme";
import type { Branding } from "../theme";
import type { AppTab, InboxConversation, InboxMessage } from "../types";
import { AccountScreen } from "../screens/AccountScreen";
import { ActivityScreen } from "../screens/ActivityScreen";
import { ChatScreen } from "../screens/ChatScreen";
import { HomeScreen } from "../screens/HomeScreen";
import { TabGlyph } from "../ui/TabGlyph";
import { Text } from "../ui/Text";

const TABS: { id: AppTab; label: string }[] = [
  { id: "home", label: "Inicio" },
  { id: "eko", label: "Eko" },
  { id: "activity", label: "Actividad" },
  { id: "account", label: "Cuenta" },
];

export function AppShell({
  branding,
  conv,
  mensajes,
  token,
  needPin,
  tab,
  onTab,
  pendingChatText,
  onQuickAction,
  onPendingConsumed,
  onChange,
  onPinSaved,
  onExit,
  connectivityRefreshKey = 0,
}: {
  branding: Branding;
  conv: InboxConversation;
  mensajes: InboxMessage[];
  token: string;
  needPin: boolean;
  tab: AppTab;
  onTab: (tab: AppTab) => void;
  pendingChatText: string;
  onQuickAction: (texto: string | null) => void;
  onPendingConsumed: () => void;
  onChange: (conv: InboxConversation | null, mensajes?: InboxMessage[]) => void;
  onPinSaved: () => void;
  onExit: () => void;
  connectivityRefreshKey?: number;
}) {
  const insets = useSafeAreaInsets();
  const bottomPad = Math.max(insets.bottom, 8);
  const [focusTicketId, setFocusTicketId] = useState("");

  const openActivity = (ticketId?: string) => {
    const tid = (ticketId || "").trim();
    if (tid) setFocusTicketId(tid);
    onTab("activity");
  };

  return (
    <View style={styles.root}>
      <View style={styles.body}>
        <View style={[styles.page, tab !== "home" && styles.hidden]} pointerEvents={tab === "home" ? "auto" : "none"}>
          <HomeScreen
            conv={conv}
            orgHint={branding.orgHint}
            token={token}
            onQuickAction={onQuickAction}
            onOpenActivity={openActivity}
            onAuthExpired={onExit}
            connectivityRefreshKey={connectivityRefreshKey}
          />
        </View>
        <View style={[styles.page, tab !== "eko" && styles.hidden]} pointerEvents={tab === "eko" ? "auto" : "none"}>
          {tab === "eko" ? (
            <ChatScreen
              branding={branding}
              conv={conv}
              mensajes={mensajes}
              token={token}
              onExit={onExit}
              onChange={onChange}
              initialText={pendingChatText}
              onInitialTextConsumed={onPendingConsumed}
            />
          ) : null}
        </View>
        <View style={[styles.page, tab !== "activity" && styles.hidden]} pointerEvents={tab === "activity" ? "auto" : "none"}>
          {tab === "activity" ? (
            <ActivityScreen
              conv={conv}
              token={token}
              onExit={onExit}
              onGoEko={() => onTab("eko")}
              focusTicketId={focusTicketId}
              onFocusConsumed={() => setFocusTicketId("")}
            />
          ) : null}
        </View>
        <View style={[styles.page, tab !== "account" && styles.hidden]} pointerEvents={tab === "account" ? "auto" : "none"}>
          <AccountScreen
            token={token}
            abonado={conv.abonado}
            needPin={needPin}
            onPinSaved={onPinSaved}
            onExit={onExit}
            onQuickAction={onQuickAction}
          />
        </View>
      </View>
      <View style={[styles.tabBar, { paddingBottom: bottomPad }]}>
        {TABS.map((item) => {
          const on = tab === item.id;
          return (
            <Pressable
              key={item.id}
              onPress={() => onTab(item.id)}
              style={[styles.tab, on && styles.tabActive]}
              accessibilityRole="tab"
              accessibilityLabel={item.label}
              accessibilityHint={`Ir a ${item.label}`}
              accessibilityState={{ selected: on }}
            >
              <TabGlyph tab={item.id} active={on} />
              <Text style={[styles.tabLabel, on && styles.tabOn]}>{item.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  body: { flex: 1 },
  page: { ...StyleSheet.absoluteFillObject },
  hidden: { display: "none" },
  tabBar: {
    flexDirection: "row",
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.tabBar,
    paddingTop: spacing.sm,
  },
  tab: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    minHeight: sizes.tab,
    paddingVertical: spacing.xs,
    marginHorizontal: spacing.xs,
    borderRadius: radius.sm,
    gap: 4,
  },
  tabActive: { backgroundColor: colors.brandMuted },
  tabLabel: { color: colors.muted, fontSize: 12, fontWeight: "600" },
  tabOn: { color: colors.brand, fontWeight: "700" },
});
