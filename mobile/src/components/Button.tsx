import React from "react";
import { ActivityIndicator, Pressable, View, ViewStyle } from "react-native";
import { Text } from "./Text";
import { Icon, IconName } from "./Icon";
import { iconSize, radius, space, useTheme } from "../theme";

type Variant = "primary" | "secondary" | "ghost" | "destructive";
type Size = "md" | "sm";

type Props = {
  title: string;
  onPress: () => void;
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  disabled?: boolean;
  loading?: boolean;
  full?: boolean;
  style?: ViewStyle;
};

export function Button({
  title,
  onPress,
  variant = "primary",
  size = "md",
  icon,
  disabled,
  loading,
  full,
  style,
}: Props) {
  const t = useTheme();
  const inactive = disabled || loading;

  const skin: Record<Variant, { bg: string; border: string; fg: string }> = {
    primary: { bg: t.fill, border: t.fill, fg: t.onFill },
    secondary: { bg: t.surface, border: t.hairline, fg: t.ink },
    ghost: { bg: "transparent", border: "transparent", fg: t.inkMuted },
    destructive: { bg: "transparent", border: t.hairline, fg: t.critical },
  };
  const { bg, border, fg } = inactive && variant === "primary"
    ? { bg: t.sunken, border: t.hairline, fg: t.inkFaint }
    : skin[variant];
  const height = size === "md" ? 48 : 38;

  return (
    <Pressable
      onPress={onPress}
      disabled={inactive}
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      android_ripple={variant === "primary" ? { color: t.overlay } : { color: t.hairline }}
      hitSlop={size === "sm" ? space.xs : undefined}
      style={({ pressed }) => [
        {
          height,
          minWidth: full ? undefined : height,
          alignSelf: full ? "stretch" : "flex-start",
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "center",
          gap: space.sm,
          paddingHorizontal: size === "md" ? space.xl : space.lg,
          borderRadius: radius.md,
          borderWidth: 1,
          backgroundColor: bg,
          borderColor: border,
          // Opacity only. Nothing here moves the layout bounds on press.
          opacity: inactive && variant !== "primary" ? 0.4 : pressed ? 0.72 : 1,
        } as ViewStyle,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} size="small" />
      ) : (
        <>
          {icon && <Icon name={icon} size={iconSize.sm} color={fg} />}
          <Text variant={size === "md" ? "bodyMedium" : "callout"} color={fg}>
            {title}
          </Text>
        </>
      )}
    </Pressable>
  );
}

/** A square icon-only control. Always needs a label, since nothing else names it. */
export function IconButton({
  name,
  label,
  onPress,
  tone = "muted",
  size = iconSize.md,
}: {
  name: IconName;
  label: string;
  onPress: () => void;
  tone?: "muted" | "critical" | "ink";
  size?: number;
}) {
  const t = useTheme();
  const color = tone === "critical" ? t.critical : tone === "ink" ? t.ink : t.inkMuted;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={space.md}
      style={({ pressed }) => ({
        width: 32,
        height: 32,
        alignItems: "center",
        justifyContent: "center",
        borderRadius: radius.full,
        opacity: pressed ? 0.5 : 1,
      })}
    >
      <Icon name={name} size={size} color={color} />
    </Pressable>
  );
}

/** The circular send control in the chat composer. */
export function SendButton({
  onPress,
  disabled,
  loading,
}: {
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  const t = useTheme();
  const inactive = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      disabled={inactive}
      accessibilityRole="button"
      accessibilityLabel="Send message"
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      hitSlop={space.sm}
      style={({ pressed }) => ({
        width: 36,
        height: 36,
        borderRadius: radius.full,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: t.fill,
        opacity: inactive ? 0.3 : pressed ? 0.75 : 1,
      })}
    >
      {loading ? (
        <ActivityIndicator color={t.onFill} size="small" />
      ) : (
        <Icon name="send" size={iconSize.md} color={t.onFill} />
      )}
    </Pressable>
  );
}

/** Two or more buttons sharing a row at equal width. */
export function ButtonRow({ children }: { children: React.ReactNode }) {
  return (
    <View style={{ flexDirection: "row", gap: space.sm }}>
      {React.Children.map(children, (child) => (
        <View style={{ flex: 1 }}>{child}</View>
      ))}
    </View>
  );
}
