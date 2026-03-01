import React, { useState } from "react";
import { TextInput, TextInputProps, View, ViewStyle } from "react-native";
import { Text } from "./Text";
import { Icon, IconName } from "./Icon";
import { IconButton } from "./Button";
import { iconSize, radius, space, type as typeScale, useTheme } from "../theme";

/** Reserved for the two things that are genuinely objects: the composer and a receipt. */
export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  const t = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: t.surface,
          borderRadius: radius.lg,
          borderWidth: 1,
          borderColor: t.hairline,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

type Tone = "neutral" | "caution" | "critical";

/** A washed note. Never a full-strength colour block. */
export function Callout({
  text,
  tone = "caution",
  icon = "alert",
  onDismiss,
}: {
  text: string;
  tone?: Tone;
  icon?: IconName;
  onDismiss?: () => void;
}) {
  const t = useTheme();
  const map: Record<Tone, { bg: string; fg: string }> = {
    neutral: { bg: t.sunken, fg: t.inkMuted },
    caution: { bg: t.cautionWash, fg: t.caution },
    critical: { bg: t.criticalWash, fg: t.critical },
  };
  const { bg, fg } = map[tone];
  return (
    <View
      accessibilityRole={tone === "critical" ? "alert" : undefined}
      style={{
        flexDirection: "row",
        alignItems: "flex-start",
        gap: space.md,
        backgroundColor: bg,
        borderRadius: radius.md,
        padding: space.md,
        marginBottom: space.sm,
      }}
    >
      <View style={{ paddingTop: 2 }}>
        <Icon name={icon} size={iconSize.sm} color={fg} />
      </View>
      <Text variant="footnote" style={{ flex: 1 }}>
        {text}
      </Text>
      {onDismiss && <IconButton name="close" label="Dismiss" onPress={onDismiss} size={iconSize.sm} />}
    </View>
  );
}

type FieldProps = TextInputProps & {
  label: string;
  hint?: string;
  error?: string;
};

/**
 * Labels stay visible above the field rather than living in the placeholder,
 * so they survive being filled in and are announced properly.
 */
export function Field({ label, hint, error, style, ...rest }: FieldProps) {
  const t = useTheme();
  const [focused, setFocused] = useState(false);
  return (
    <View style={{ marginBottom: space.lg }}>
      <Text variant="caption" tone="muted" style={{ marginBottom: 6 }}>
        {label}
      </Text>
      <TextInput
        {...rest}
        accessibilityLabel={label}
        placeholderTextColor={t.inkFaint}
        onFocus={(e) => {
          setFocused(true);
          rest.onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          rest.onBlur?.(e);
        }}
        style={[
          typeScale.body,
          {
            backgroundColor: t.surface,
            borderRadius: radius.md,
            borderWidth: 1,
            borderColor: error ? t.critical : focused ? t.hairlineStrong : t.hairline,
            paddingHorizontal: space.md,
            paddingVertical: space.md,
            minHeight: 48,
            color: t.ink,
          },
          style,
        ]}
      />
      {!!hint && !error && (
        <Text variant="caption" tone="faint" style={{ marginTop: 6 }}>
          {hint}
        </Text>
      )}
      {!!error && (
        <Text variant="caption" tone="critical" style={{ marginTop: 6 }}>
          {error}
        </Text>
      )}
    </View>
  );
}

/** A single number given room to breathe, with a thin track underneath it. */
export function Stat({
  value,
  suffix,
  caption,
  ratio,
}: {
  value: string;
  suffix?: string;
  caption?: string;
  ratio?: number;
}) {
  const t = useTheme();
  return (
    <View style={{ padding: space.lg }}>
      <View style={{ flexDirection: "row", alignItems: "baseline", gap: space.xs }}>
        <Text variant="display">{value}</Text>
        {!!suffix && (
          <Text variant="callout" tone="muted">
            {suffix}
          </Text>
        )}
      </View>
      {ratio != null && (
        <View
          style={{
            height: 4,
            borderRadius: radius.full,
            backgroundColor: t.sunken,
            marginTop: space.md,
            overflow: "hidden",
          }}
        >
          <View
            style={{
              width: `${Math.max(0, Math.min(1, ratio)) * 100}%`,
              height: "100%",
              borderRadius: radius.full,
              backgroundColor: t.ink,
            }}
          />
        </View>
      )}
      {!!caption && (
        <Text variant="footnote" tone="muted" style={{ marginTop: space.sm }}>
          {caption}
        </Text>
      )}
    </View>
  );
}
