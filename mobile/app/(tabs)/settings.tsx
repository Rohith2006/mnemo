import React from "react";
import { Alert, Platform, ScrollView, Switch, useWindowDimensions, View } from "react-native";
import { useAuth } from "../../src/auth/AuthContext";
import { useForget, useUpdateMe } from "../../src/api/hooks";
import { Group, Row, SectionHeader } from "../../src/components/List";
import { MnemoMark } from "../../src/components/Logo";
import { contentPadding, LargeTitle, Screen, TopBar, useScrollHeader } from "../../src/components/Screen";
import { Text } from "../../src/components/Text";
import { space, useTheme } from "../../src/theme";

export default function SettingsScreen() {
  const t = useTheme();
  const { width } = useWindowDimensions();
  const pad = contentPadding(width);
  const { scrolled, scrollProps } = useScrollHeader();

  const { user, serverUrl, logout, refreshMe } = useAuth();
  const forget = useForget();
  const updateMe = useUpdateMe();

  const togglePush = (value: boolean) => {
    updateMe.mutate({ push_enabled: value }, { onSuccess: () => refreshMe() });
  };

  const confirmForget = () => {
    const message =
      "This deletes every fact, log entry, task, habit, mood entry and reminder. It cannot be undone.";
    // Alert.alert is a no-op on react-native-web (it renders nothing and never
    // calls back) — window.confirm is the platform-correct equivalent there.
    if (Platform.OS === "web") {
      if (window.confirm(`Erase everything?\n\n${message}`)) forget.mutate();
      return;
    }
    Alert.alert("Erase everything?", message, [
      { text: "Cancel", style: "cancel" },
      { text: "Erase", style: "destructive", onPress: () => forget.mutate() },
    ]);
  };

  return (
    <Screen>
      <TopBar title="Settings" showTitle={scrolled} />
      <ScrollView
        {...scrollProps}
        contentContainerStyle={{ paddingHorizontal: pad, paddingTop: space.xxl, paddingBottom: space.huge }}
      >
        <LargeTitle title="Settings" />

        <SectionHeader title="Account" />
        <Group style={{ marginBottom: space.xxxl }}>
          <Row first icon="user" title="Name" value={user?.name || "Not set"} />
          <Row icon="email" title="Email" value={user?.email || "Not set"} />
          <Row icon="timezone" title="Timezone" value={user?.tz || "Not set"} />
          <Row
            icon="reminder"
            title="Push notifications"
            trailing={
              <Switch
                value={!!user?.push_enabled}
                onValueChange={togglePush}
                disabled={updateMe.isPending}
              />
            }
          />
          <Row icon="server" title="Server" value={serverUrl || "Not set"} />
        </Group>

        <SectionHeader title="Session" />
        <Group style={{ marginBottom: space.xxxl }}>
          <Row first icon="logout" title="Log out" onPress={logout} />
        </Group>

        <SectionHeader title="Data" />
        <Group>
          <Row
            first
            icon="wipe"
            iconColor={t.critical}
            titleTone="critical"
            title={forget.isPending ? "Erasing" : "Erase everything"}
            onPress={confirmForget}
          />
        </Group>

        <View style={{ alignItems: "center", marginTop: space.huge, gap: space.sm }}>
          <MnemoMark size={20} color={t.inkFaint} />
          <Text variant="caption" tone="faint">
            mnemo 1.0.0
          </Text>
        </View>
      </ScrollView>
    </Screen>
  );
}
