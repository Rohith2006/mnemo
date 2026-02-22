import React, { useEffect } from "react";
import { ActivityIndicator, View } from "react-native";
import { useRouter, useSegments } from "expo-router";
import { useAuth } from "./AuthContext";
import { useTheme } from "../theme";

/** Redirects between the (auth) group and (tabs) group based on sign-in state. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { loading, user } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  const t = useTheme();

  useEffect(() => {
    if (loading) return;
    const inAuthGroup = segments[0] === "(auth)";
    if (!user && !inAuthGroup) {
      router.replace("/(auth)/login");
    } else if (user && inAuthGroup) {
      router.replace("/(tabs)");
    }
  }, [loading, user, segments, router]);

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: t.bg }}>
        <ActivityIndicator color={t.accent} size="large" />
      </View>
    );
  }

  return <>{children}</>;
}
