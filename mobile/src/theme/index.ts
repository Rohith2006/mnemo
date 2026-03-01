import { useColorScheme } from "react-native";
import { palettes, type Palette } from "./tokens";

export * from "./tokens";
export * from "./typography";

export type Theme = Palette;

export function useScheme(): "light" | "dark" {
  return useColorScheme() === "dark" ? "dark" : "light";
}

export function useTheme(): Theme {
  return palettes[useScheme()];
}
