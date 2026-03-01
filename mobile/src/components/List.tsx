import React from "react";
import { Pressable, View, ViewStyle } from "react-native";
import { Text } from "./Text";
import { Icon, IconName } from "./Icon";
import { HIT, iconSize, radius, space, useTheme } from "../theme";

/** Small uppercase label that opens a group. */
export function SectionHeader({
  title,
  trailing,
  style,
}: {
  title: string;
  trailing?: React.ReactNode;
  style?: ViewStyle;
}) {
  return (
    <View
      style={[
        { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: space.md },
        style,
      ]}
    >
      <Text variant="overline" tone="muted" style={{ textTransform: "uppercase" }}>
        {title}
      </Text>
      {trailing}
    </View>
  );
}

/** The grouped container. Rows inside it separate themselves with hairlines. */
export function Group({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  const t = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: t.surface,
          borderRadius: radius.lg,
          borderWidth: 1,
          borderColor: t.hairline,
          overflow: "hidden",
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

export function Row({
  icon,
  iconColor,
  title,
  subtitle,
  value,
  valueTone = "muted",
  valueMono,
  first,
  onPress,
  onLongPress,
  accessibilityLabel,
  trailing,
  leading,
  titleTone = "default",
}: {
  icon?: IconName;
  iconColor?: string;
  title: string;
  subtitle?: string;
  value?: string;
  valueTone?: "muted" | "positive" | "caution" | "critical" | "default";
  valueMono?: boolean;
  first?: boolean;
  onPress?: () => void;
  onLongPress?: () => void;
  accessibilityLabel?: string;
  trailing?: React.ReactNode;
  leading?: React.ReactNode;
  titleTone?: "default" | "critical";
}) {
  const t = useTheme();

  const body = (pressed: boolean) => (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: space.md,
        minHeight: HIT,
        paddingVertical: space.md,
        paddingHorizontal: space.lg,
        borderTopWidth: first ? 0 : 1,
        borderTopColor: t.hairline,
        backgroundColor: pressed ? t.sunken : "transparent",
      }}
    >
      {leading}
      {!leading && icon && <Icon name={icon} size={iconSize.md} color={iconColor ?? t.inkFaint} />}
      <View style={{ flex: 1 }}>
        <Text variant="body" tone={titleTone === "critical" ? "critical" : "default"} numberOfLines={2}>
          {title}
        </Text>
        {!!subtitle && (
          <Text variant="footnote" tone="muted" style={{ marginTop: 2 }}>
            {subtitle}
          </Text>
        )}
      </View>
      {!!value && (
        // A long value (a server URL, an email) truncates rather than crowding the title.
        <Text variant={valueMono ? "mono" : "footnote"} tone={valueTone} numberOfLines={1}>
          {value}
        </Text>
      )}
      {trailing}
    </View>
  );

  if (!onPress && !onLongPress) return body(false);

  return (
    <Pressable
      onPress={onPress}
      onLongPress={onLongPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? title}
      android_ripple={{ color: t.hairline }}
      style={({ pressed }) => ({ opacity: pressed ? 0.99 : 1 })}
    >
      {({ pressed }) => body(pressed)}
    </Pressable>
  );
}

/** Sits under a group to explain an interaction that has no visible affordance. */
export function GroupFootnote({ children }: { children: React.ReactNode }) {
  return (
    <Text variant="caption" tone="faint" style={{ marginTop: space.sm, paddingHorizontal: space.xs }}>
      {children}
    </Text>
  );
}

export function EmptyRow({ children }: { children: React.ReactNode }) {
  return (
    <View style={{ paddingVertical: space.lg, paddingHorizontal: space.lg }}>
      <Text variant="callout" tone="faint">
        {children}
      </Text>
    </View>
  );
}

export function Chip({ children }: { children: string }) {
  const t = useTheme();
  return (
    <View
      style={{
        backgroundColor: t.sunken,
        borderRadius: radius.full,
        paddingVertical: 6,
        paddingHorizontal: space.md,
      }}
    >
      <Text variant="footnote" tone="muted">
        {children}
      </Text>
    </View>
  );
}
