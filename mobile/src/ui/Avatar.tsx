import { Image, StyleSheet } from "react-native";

type Size = "sm" | "md" | "lg";

const SIZES: Record<Size, number> = {
  sm: 28,
  md: 36,
  lg: 88,
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
