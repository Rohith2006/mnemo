import { useColorScheme } from "react-native";

const light = {
  bg: "#F5F3EF",
  surface: "#FFFFFF",
  surfaceAlt: "#EFEBE3",
  border: "#E2DCD1",
  text: "#241F16",
  textMuted: "#8A8072",
  accent: "#B5622E", // warm terracotta — deliberately not "chat app blue"
  accentSoft: "#F1DDCB",
  success: "#4B7A5B",
  warn: "#C08A2E",
  danger: "#B0473F",
};

const dark = {
  bg: "#17140F",
  surface: "#221E17",
  surfaceAlt: "#2B2620",
  border: "#3A342B",
  text: "#F2EEE6",
  textMuted: "#A79E8E",
  accent: "#E08A4F",
  accentSoft: "#3A2A1C",
  success: "#6FAE83",
  warn: "#D9A54B",
  danger: "#E07A70",
};

export type Theme = typeof light;

export function useTheme(): Theme {
  const scheme = useColorScheme();
  return scheme === "dark" ? dark : light;
}

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };
export const radius = { sm: 8, md: 12, lg: 18, pill: 999 };
