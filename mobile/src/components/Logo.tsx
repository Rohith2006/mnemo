import React from "react";
import { View } from "react-native";
import Svg, { Circle, Path } from "react-native-svg";
import { Text } from "./Text";
import { space, useTheme } from "../theme";

/**
 * The mark is an "m" drawn as a single thread, with its left foot terminating
 * in a filled node: one memory pinned down, the rest of the line continuing.
 * Single stroke, currentColor, so it themes with everything else.
 */
export function MnemoMark({ size = 24, color }: { size?: number; color?: string }) {
  const t = useTheme();
  const stroke = color ?? t.ink;
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M3.6 20.4V10.9a4.2 4.2 0 0 1 8.4 0v9.5"
        stroke={stroke}
        strokeWidth={1.9}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Path
        d="M12 10.9a4.2 4.2 0 0 1 8.4 0v9.5"
        stroke={stroke}
        strokeWidth={1.9}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Circle cx={3.6} cy={20.4} r={1.9} fill={stroke} />
    </Svg>
  );
}

export function Wordmark({ size = 20, color }: { size?: number; color?: string }) {
  return (
    <View
      style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}
      accessible
      accessibilityRole="header"
      accessibilityLabel="mnemo"
    >
      <MnemoMark size={size} color={color} />
      <Text variant="headline" color={color} style={{ letterSpacing: -0.4 }}>
        mnemo
      </Text>
    </View>
  );
}
