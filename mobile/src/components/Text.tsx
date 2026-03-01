import React from "react";
import { Text as RNText, TextProps, TextStyle } from "react-native";
import { type as typeScale, TypeVariant, useTheme } from "../theme";

type Props = TextProps & {
  variant?: TypeVariant;
  /** Semantic role, resolved against the palette. Overridden by `color`. */
  tone?: "default" | "muted" | "faint" | "positive" | "caution" | "critical" | "inverted";
  color?: string;
};

/**
 * Every piece of text in the app goes through here, so there is exactly one
 * place where a size, weight or ink value can be chosen.
 */
export function Text({ variant = "body", tone = "default", color, style, ...rest }: Props) {
  const t = useTheme();
  const tones: Record<NonNullable<Props["tone"]>, string> = {
    default: t.ink,
    muted: t.inkMuted,
    faint: t.inkFaint,
    positive: t.positive,
    caution: t.caution,
    critical: t.critical,
    inverted: t.onFill,
  };
  const base = typeScale[variant] as TextStyle;
  return <RNText {...rest} style={[base, { color: color ?? tones[tone] }, style]} />;
}
