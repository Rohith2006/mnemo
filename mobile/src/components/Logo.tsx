import React, { useEffect, useRef, useState } from "react";
import { AccessibilityInfo, Animated, Platform, View } from "react-native";
import Svg, { Circle, Path } from "react-native-svg";
import { Text } from "./Text";
import { space, useTheme } from "../theme";

/**
 * The mark is an "m" drawn as a single thread, with its left foot terminating
 * in a filled node: one memory pinned down, the rest of the line continuing.
 * Single stroke, currentColor, so it themes with everything else.
 *
 * `animated` adds a slow, subtle breathing scale/opacity loop, for the Chat
 * landing state — off by default so every other call site (Wordmark, the
 * Settings footer, Chat's old empty state) is unaffected.
 */
export function MnemoMark({
  size = 24,
  color,
  animated = false,
}: {
  size?: number;
  color?: string;
  animated?: boolean;
}) {
  const t = useTheme();
  const stroke = color ?? t.ink;
  const pulse = useRef(new Animated.Value(0)).current;
  // Reduce-motion falls all the way back to the plain, fully-opaque, normal-
  // scale svg below (not just "animation paused mid-cycle") — the breathing
  // loop's resting point (pulse=0) is deliberately dimmer/smaller than that,
  // so freezing on it instead of falling back would leave the mark looking
  // permanently faded for users who asked for less motion.
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    if (!animated) return;
    let cancelled = false;
    let loop: Animated.CompositeAnimation | null = null;
    AccessibilityInfo.isReduceMotionEnabled().then((reduced) => {
      if (cancelled) return;
      if (reduced) {
        setReducedMotion(true);
        return;
      }
      loop = Animated.loop(
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1, duration: 1400, useNativeDriver: Platform.OS !== "web" }),
          Animated.timing(pulse, { toValue: 0, duration: 1400, useNativeDriver: Platform.OS !== "web" }),
        ]),
      );
      loop.start();
    });
    return () => {
      cancelled = true;
      loop?.stop();
    };
  }, [animated, pulse]);

  const svg = (
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

  if (!animated || reducedMotion) return svg;

  const scale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.06] });
  const opacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.85, 1] });
  return <Animated.View style={{ transform: [{ scale }], opacity }}>{svg}</Animated.View>;
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
