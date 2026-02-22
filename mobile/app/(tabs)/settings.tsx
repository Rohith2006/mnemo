import React from "react";
import { Alert, ScrollView, Text, View } from "react-native";
import { useAuth } from "../../src/auth/AuthContext";
import { useForget } from "../../src/api/hooks";
import { Card, GhostButton, SectionLabel } from "../../src/components/Primitives";
import { useTheme, spacing } from "../../src/theme";

export default function SettingsScreen() {
  const t = useTheme();
  const { user, serverUrl, logout } = useAuth();
  const forget = useForget();

  const confirmForget = () => {
    Alert.alert("Wipe everything?", "This deletes all facts, logs, tasks, habits, mood entries, and reminders. This can't be undone.",
      [{ text: "Cancel", style: "cancel" }, { text: "Wipe it", style: "destructive", onPress: () => forget.mutate() }]);
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: t.bg }} contentContainerStyle={{ padding: spacing.lg }}>
      <SectionLabel>Account</SectionLabel>
      <Card style={{ marginBottom: spacing.lg }}>
        <Row label="Name" value={user?.name || "—"} />
        <Row label="Email" value={user?.email || "—"} />
        <Row label="Timezone" value={user?.tz || "—"} />
        <Row label="Server" value={serverUrl || "—"} last />
      </Card>

      <SectionLabel>Session</SectionLabel>
      <View style={{ marginBottom: spacing.lg }}>
        <GhostButton title="Log out" onPress={logout} />
      </View>

      <SectionLabel>Danger zone</SectionLabel>
      <GhostButton title={forget.isPending ? "Wiping…" : "Forget everything"} onPress={confirmForget} danger />
    </ScrollView>
  );
}

function Row({ label, value, last }: { label: string; value: string; last?: boolean }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 8,
      borderBottomWidth: last ? 0 : 1, borderBottomColor: t.border }}>
      <Text style={{ color: t.textMuted, fontSize: 14 }}>{label}</Text>
      <Text style={{ color: t.text, fontSize: 14 }}>{value}</Text>
    </View>
  );
}
