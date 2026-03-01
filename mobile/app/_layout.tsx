import React from "react";
import { View } from "react-native";
import { Slot } from "expo-router";
import { useFonts } from "expo-font";
import { QueryClientProvider } from "@tanstack/react-query";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { queryClient } from "../src/queryClient";
import { AuthProvider } from "../src/auth/AuthContext";
import { AuthGate } from "../src/auth/AuthGate";
import { fontAssets, palettes } from "../src/theme";

export default function RootLayout() {
  // Resolves immediately off Android, where the asset map is empty.
  const [fontsReady] = useFonts(fontAssets);

  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <StatusBar style="auto" />
          {fontsReady ? (
            <AuthGate>
              <Slot />
            </AuthGate>
          ) : (
            <View style={{ flex: 1, backgroundColor: palettes.light.canvas }} />
          )}
        </AuthProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
