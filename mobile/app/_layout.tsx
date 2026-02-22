import React from "react";
import { Slot } from "expo-router";
import { QueryClientProvider } from "@tanstack/react-query";
import { StatusBar } from "expo-status-bar";
import { queryClient } from "../src/queryClient";
import { AuthProvider } from "../src/auth/AuthContext";
import { AuthGate } from "../src/auth/AuthGate";

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <StatusBar style="auto" />
        <AuthGate>
          <Slot />
        </AuthGate>
      </AuthProvider>
    </QueryClientProvider>
  );
}
