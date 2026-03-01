import React from "react";
import { ColorValue, Platform } from "react-native";
import { Tabs } from "expo-router";
import { Icon, IconName } from "../../src/components/Icon";
import { font, iconSize, useTheme } from "../../src/theme";

/**
 * Headers are off: every screen renders its own large title, so the compact
 * bar can materialise only once you have scrolled past it.
 */
export default function TabsLayout() {
  const t = useTheme();

  const tab = (name: IconName) =>
    ({ color }: { color: ColorValue }) => <Icon name={name} size={iconSize.lg} color={String(color)} />;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: t.canvas,
          borderTopColor: t.hairline,
          borderTopWidth: 1,
          elevation: 0,
          height: Platform.OS === "ios" ? 84 : 62,
          paddingTop: 6,
        },
        tabBarActiveTintColor: t.ink,
        tabBarInactiveTintColor: t.inkFaint,
        tabBarLabelStyle: { fontSize: 11, letterSpacing: 0, ...font(500) },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Capture", tabBarIcon: tab("capture") }} />
      <Tabs.Screen name="track" options={{ title: "Track", tabBarIcon: tab("track") }} />
      <Tabs.Screen name="chat" options={{ title: "Chat", tabBarIcon: tab("chat") }} />
      <Tabs.Screen name="settings" options={{ title: "Settings", tabBarIcon: tab("settings") }} />
    </Tabs>
  );
}
