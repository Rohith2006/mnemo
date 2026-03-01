import { Platform, TextStyle } from "react-native";

/**
 * SF Pro is the system face on Apple platforms, so `System` on iOS and the
 * system stack on web both resolve to the real thing on Apple hardware. It
 * cannot ship anywhere else, so Android bundles Inter instead, which is close
 * enough that the app reads as one design across platforms.
 *
 * React Native on Android does not synthesise weights for a bundled family, so
 * each weight is registered as its own family and `font()` does the mapping.
 */

export type Weight = 400 | 500 | 600 | 700;

const INTER: Record<Weight, string> = {
  400: "Inter_400Regular",
  500: "Inter_500Medium",
  600: "Inter_600SemiBold",
  700: "Inter_700Bold",
};

/** Loaded at launch by the root layout. Empty off Android, which needs no bundle. */
export const fontAssets: Record<string, number> = Platform.OS === "android" ? {
  Inter_400Regular: require("@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf"),
  Inter_500Medium: require("@expo-google-fonts/inter/500Medium/Inter_500Medium.ttf"),
  Inter_600SemiBold: require("@expo-google-fonts/inter/600SemiBold/Inter_600SemiBold.ttf"),
  Inter_700Bold: require("@expo-google-fonts/inter/700Bold/Inter_700Bold.ttf"),
} : {};

/** Resolves to SF Pro on Apple hardware, and to the platform default elsewhere. */
const WEB_STACK = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif';

export function font(weight: Weight = 400): TextStyle {
  const fontWeight = String(weight) as TextStyle["fontWeight"];
  if (Platform.OS === "ios") return { fontFamily: "System", fontWeight };
  if (Platform.OS === "android") return { fontFamily: INTER[weight] };
  return { fontFamily: WEB_STACK, fontWeight };
}

export const monoFamily = Platform.select({
  ios: "Menlo",
  android: "monospace",
  default: "ui-monospace, SFMono-Regular, Menlo, monospace",
}) as string;

/**
 * Sizes track the iOS type scale so Dynamic Type scaling stays predictable.
 * Negative tracking on the large sizes only, the way SF is meant to be set.
 */
export const type = {
  display: { fontSize: 32, lineHeight: 38, letterSpacing: -0.7, ...font(700) },
  title: { fontSize: 22, lineHeight: 28, letterSpacing: -0.4, ...font(600) },
  headline: { fontSize: 17, lineHeight: 22, letterSpacing: -0.2, ...font(600) },
  body: { fontSize: 16, lineHeight: 23, letterSpacing: -0.1, ...font(400) },
  bodyMedium: { fontSize: 16, lineHeight: 23, letterSpacing: -0.1, ...font(500) },
  callout: { fontSize: 15, lineHeight: 21, ...font(400) },
  footnote: { fontSize: 13, lineHeight: 18, ...font(400) },
  caption: { fontSize: 12, lineHeight: 16, ...font(500) },
  overline: { fontSize: 11, lineHeight: 14, letterSpacing: 0.7, ...font(600) },
  mono: { fontSize: 12, lineHeight: 16, fontFamily: monoFamily },
  monoSmall: { fontSize: 11, lineHeight: 14, fontFamily: monoFamily },
} as const;

export type TypeVariant = keyof typeof type;
