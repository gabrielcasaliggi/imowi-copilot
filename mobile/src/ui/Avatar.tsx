import { Image, StyleSheet } from "react-native";

import { sizes } from "../theme";

type Size = "sm" | "md" | "lg";

const SIZES: Record<Size, number> = {
  sm: sizes.avatarSm,
  md: sizes.avatarMd,
  lg: sizes.avatarLg,
};

export function Avatar({
  size = "md",
  accessibilityLabel = "Eko",
}: {
  size?: Size;
  accessibilityLabel?: string;
}) {
  const dim = SIZES[size];
  return (
    <Image
      source={require("../../assets/icon.png")}
      style={[styles.img, { width: dim, height: dim, borderRadius: dim / 2 }]}
      accessibilityLabel={accessibilityLabel}
    />
  );
}

const styles = StyleSheet.create({
  img: {},
});
