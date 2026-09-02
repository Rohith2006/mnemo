import React, { useEffect, useState } from "react";
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  RefreshControl,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";
import { useCapture, useDashboard, useDigest } from "../../src/api/hooks";
import { ApiError } from "../../src/api/client";
import { Button, ButtonRow, IconButton } from "../../src/components/Button";
import { Icon } from "../../src/components/Icon";
import { SectionHeader } from "../../src/components/List";
import { Wordmark } from "../../src/components/Logo";
import { Receipt } from "../../src/components/Receipt";
import { contentPadding, LargeTitle, Screen, TopBar, useScrollHeader } from "../../src/components/Screen";
import { Callout, Card } from "../../src/components/Surfaces";
import { Text } from "../../src/components/Text";
import { reconcile } from "../../src/notifications";
import { registerForPush } from "../../src/notifications/push";
import { stripMarkdown } from "../../src/utils/text";
import { iconSize, space, type as typeScale, useTheme } from "../../src/theme";
import type { CaptureResponse } from "../../src/api/types";

type ReceiptEntry = { id: string; at: number; text: string; result: CaptureResponse };

const PROMPT = "Ran 5k this morning, felt good. Remind me to call mom at 6.";

export default function CaptureScreen() {
  const t = useTheme();
  const { width } = useWindowDimensions();
  const pad = contentPadding(width);
  const { scrolled, scrollProps } = useScrollHeader();

  const { data: dash, refetch, isRefetching } = useDashboard();
  const capture = useCapture();
  const briefing = useDigest("morning");
  const insights = useDigest("ondemand");

  const [text, setText] = useState("");
  const [receipts, setReceipts] = useState<ReceiptEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [digest, setDigest] = useState<{ title: string; text: string } | null>(null);

  useEffect(() => {
    if (dash?.reminders?.length) reconcile(dash.reminders);
    // Self-heals a push-token registration that was pruned (correctly, e.g.
    // after a reinstall, or incorrectly by a since-fixed bug) — this is
    // idempotent server-side (ON CONFLICT(token) DO UPDATE in store.py), so
    // calling it on every dashboard load is safe and cheap.
    registerForPush();
  }, [dash?.reminders]);

  const submit = () => {
    const value = text.trim();
    if (!value) return;
    setError(null);
    capture.mutate(value, {
      onSuccess: (result) => {
        setReceipts((prev) => [{ id: `${Date.now()}`, at: Date.now(), text: value, result }, ...prev]);
        setText("");
      },
      onError: (e) => setError(e instanceof ApiError ? e.message : "That did not go through. Try again."),
    });
  };

  const openDigest = (kind: "morning" | "ondemand") => {
    const mutation = kind === "morning" ? briefing : insights;
    setError(null);
    mutation.mutate(false, {
      onSuccess: (d) =>
        setDigest({ title: kind === "morning" ? "Briefing" : "Insights", text: stripMarkdown(d.text) }),
      onError: (e) =>
        setError(e instanceof ApiError ? e.message : "Could not put that together right now."),
    });
  };

  return (
    <Screen>
      <TopBar
        title="Capture"
        showTitle={scrolled}
        leading={<Wordmark size={20} />}
        trailing={
          <Text variant="footnote" tone="faint">
            {today()}
          </Text>
        }
      />
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={90}
      >
        <FlatList
          {...scrollProps}
          data={receipts}
          keyExtractor={(item) => item.id}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ paddingHorizontal: pad, paddingTop: space.xxl, paddingBottom: space.huge }}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={t.inkFaint} />
          }
          renderItem={({ item }) => <Receipt text={item.text} at={item.at} result={item.result} />}
          ListHeaderComponent={
            <View>
              <LargeTitle title="Capture" />

              {dash?.alerts.map((a, i) => (
                <Callout key={i} text={a} tone="caution" />
              ))}
              {!!error && <Callout text={error} tone="critical" icon="alert" />}

              <Card style={{ marginTop: dash?.alerts.length || error ? space.md : 0 }}>
                <TextInput
                  value={text}
                  onChangeText={setText}
                  placeholder={PROMPT}
                  placeholderTextColor={t.inkFaint}
                  multiline
                  accessibilityLabel="What happened"
                  style={[
                    typeScale.body,
                    { color: t.ink, padding: space.lg, minHeight: 104, textAlignVertical: "top" },
                    // The browser's default focus ring on a web <textarea> would
                    // otherwise show alongside this component's own border —
                    // an RNW-only style extension @types/react-native doesn't model.
                    { outlineStyle: "none" } as object,
                  ]}
                />
                {/* The placeholder already demonstrates what this understands,
                    so the row underneath carries the action and nothing else. */}
                <View
                  style={{
                    flexDirection: "row",
                    justifyContent: "flex-end",
                    borderTopWidth: 1,
                    borderTopColor: t.hairline,
                    padding: space.md,
                  }}
                >
                  <Button
                    title="Log it"
                    size="sm"
                    onPress={submit}
                    disabled={!text.trim()}
                    loading={capture.isPending}
                  />
                </View>
              </Card>

              <View style={{ marginTop: space.md }}>
                <ButtonRow>
                  <Button
                    title="Briefing"
                    icon="briefing"
                    variant="secondary"
                    size="sm"
                    full
                    loading={briefing.isPending}
                    onPress={() => openDigest("morning")}
                  />
                  <Button
                    title="Insights"
                    icon="insight"
                    variant="secondary"
                    size="sm"
                    full
                    loading={insights.isPending}
                    onPress={() => openDigest("ondemand")}
                  />
                </ButtonRow>
              </View>

              {digest && (
                <Card style={{ marginTop: space.md, padding: space.lg }}>
                  <View
                    style={{
                      flexDirection: "row",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: space.sm,
                    }}
                  >
                    <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
                      <Icon
                        name={digest.title === "Briefing" ? "briefing" : "insight"}
                        size={iconSize.sm}
                        color={t.inkMuted}
                      />
                      <Text variant="overline" tone="muted" style={{ textTransform: "uppercase" }}>
                        {digest.title}
                      </Text>
                    </View>
                    <IconButton name="close" label="Close briefing" onPress={() => setDigest(null)} />
                  </View>
                  <Text variant="callout">{digest.text}</Text>
                </Card>
              )}

              {receipts.length > 0 && (
                <SectionHeader
                  title="This session"
                  style={{ marginTop: space.xxxl }}
                  trailing={
                    <Text variant="mono" tone="faint">
                      {receipts.length}
                    </Text>
                  }
                />
              )}
            </View>
          }
          ListEmptyComponent={
            <View style={{ marginTop: space.xxxl, alignItems: "center", gap: space.sm }}>
              <Icon name="capture" size={iconSize.lg} color={t.inkFaint} />
              <Text variant="callout" tone="faint" style={{ textAlign: "center" }}>
                Anything you write here gets sorted and kept.
              </Text>
            </View>
          }
        />
      </KeyboardAvoidingView>
    </Screen>
  );
}

function today() {
  return new Date().toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
}
