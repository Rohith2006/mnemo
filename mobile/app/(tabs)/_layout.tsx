import React from "react";
import { Text } from "react-native";
import { Tabs } from "expo-router";
import { useTheme } from "../../src/theme";

function TabIcon({ emoji, focused }: { emoji: string; focused: boolean }) {
  return <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.5 }}>{emoji}</Text>;
}

export default function TabsLayout() {
  const t = useTheme();
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: t.bg },
        headerShadowVisible: false,
        headerTitleStyle: { color: t.text },
        tabBarStyle: { backgroundColor: t.surface, borderTopColor: t.border },
        tabBarActiveTintColor: t.accent,
        tabBarInactiveTintColor: t.textMuted,
      }}
    >
      <Tabs.Screen name="index" options={{
        title: "Capture", headerTitle: "mnemo",
        tabBarIcon: ({ focused }) => <TabIcon emoji="✏️" focused={focused} />,
      }} />
      <Tabs.Screen name="track" options={{
        title: "Track", headerTitle: "What I'm tracking",
        tabBarIcon: ({ focused }) => <TabIcon emoji="📊" focused={focused} />,
      }} />
      <Tabs.Screen name="chat" options={{
        title: "Chat", headerTitle: "Talk to mnemo",
        tabBarIcon: ({ focused }) => <TabIcon emoji="💬" focused={focused} />,
      }} />
      <Tabs.Screen name="settings" options={{
        title: "Settings", headerTitle: "Settings",
        tabBarIcon: ({ focused }) => <TabIcon emoji="⚙️" focused={focused} />,
      }} />
    </Tabs>
  );
}
