import React, { useCallback, useState } from "react";
import { NativeScrollEvent, NativeSyntheticEvent, View, ViewStyle } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Text } from "./Text";
import { space, useTheme } from "../theme";

/**
 * Apple-style large titles: the title lives in the scroll content and the top
 * bar picks it up once you scroll past it, materialising a hairline at the
 * same moment. A plain boolean is enough here, the switch happens well inside
 * a frame and reads as instant rather than as a pop.
 */
export function useScrollHeader(threshold = 12) {
  const [scrolled, setScrolled] = useState(false);
  const onScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const past = e.nativeEvent.contentOffset.y > threshold;
      setScrolled((prev) => (prev === past ? prev : past));
    },
    [threshold],
  );
  return { scrolled, scrollProps: { onScroll, scrollEventThrottle: 16 } };
}

export function Screen({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  const t = useTheme();
  return <View style={[{ flex: 1, backgroundColor: t.canvas }, style]}>{children}</View>;
}

export function TopBar({
  title,
  showTitle,
  leading,
  trailing,
}: {
  title: string;
  showTitle: boolean;
  leading?: React.ReactNode;
  trailing?: React.ReactNode;
}) {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View
      style={{
        paddingTop: insets.top,
        backgroundColor: t.canvas,
        borderBottomWidth: 1,
        borderBottomColor: showTitle ? t.hairline : "transparent",
      }}
    >
      <View
        style={{
          height: 48,
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          paddingHorizontal: space.xl,
        }}
      >
        <View style={{ flex: 1, alignItems: "flex-start" }}>{!showTitle && leading}</View>
        <View style={{ flex: 2, alignItems: "center" }}>
          {showTitle && (
            <Text variant="headline" numberOfLines={1}>
              {title}
            </Text>
          )}
        </View>
        <View style={{ flex: 1, alignItems: "flex-end" }}>{trailing}</View>
      </View>
    </View>
  );
}

export function LargeTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <View style={{ marginBottom: space.xxl }} accessibilityRole="header">
      <Text variant="display">{title}</Text>
      {!!subtitle && (
        <Text variant="callout" tone="muted" style={{ marginTop: space.xs }}>
          {subtitle}
        </Text>
      )}
    </View>
  );
}

/** Horizontal page inset. Widens a little on tablets so text keeps its measure. */
export function contentPadding(width: number) {
  return width >= 700 ? space.huge : space.xl;
}
