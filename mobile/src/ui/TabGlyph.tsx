import { StyleSheet, View } from "react-native";

import { colors, sizes } from "../theme";
import type { AppTab } from "../types";

export function TabGlyph({
  tab,
  active,
}: {
  tab: AppTab;
  active: boolean;
}) {
  const c = active ? colors.brand : colors.muted;
  if (tab === "home") {
    return (
      <View style={styles.box}>
        <View style={[styles.roof, { borderBottomColor: c }]} />
        <View style={[styles.house, { backgroundColor: c }]} />
      </View>
    );
  }
  if (tab === "eko") {
    return <View style={[styles.dot, { backgroundColor: c }]} />;
  }
  if (tab === "activity") {
    return (
      <View style={styles.box}>
        <View style={[styles.bar, { backgroundColor: c }]} />
        <View style={[styles.barShort, { backgroundColor: c }]} />
        <View style={[styles.bar, { backgroundColor: c }]} />
      </View>
    );
  }
  return (
    <View style={styles.box}>
      <View style={[styles.head, { borderColor: c }]} />
      <View style={[styles.shoulders, { borderColor: c }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    width: sizes.icon,
    height: sizes.icon,
    alignItems: "center",
    justifyContent: "center",
  },
  roof: {
    width: 0,
    height: 0,
    borderLeftWidth: 7,
    borderRightWidth: 7,
    borderBottomWidth: 6,
    borderLeftColor: "transparent",
    borderRightColor: "transparent",
  },
  house: { width: 12, height: 8, marginTop: 1, borderRadius: 1 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  bar: { width: 14, height: 2, borderRadius: 1, marginVertical: 1.5 },
  barShort: { width: 10, height: 2, borderRadius: 1, marginVertical: 1.5, alignSelf: "flex-start", marginLeft: 4 },
  head: { width: 8, height: 8, borderRadius: 4, borderWidth: 1.5 },
  shoulders: {
    width: 14,
    height: 7,
    borderWidth: 1.5,
    borderTopLeftRadius: 7,
    borderTopRightRadius: 7,
    borderBottomWidth: 0,
    marginTop: 1,
  },
});
