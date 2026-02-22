import React, { useEffect, useState } from "react";
import { FlatList, KeyboardAvoidingView, Platform, Pressable, RefreshControl, Text, View } from "react-native";
import { useDashboard, useCapture, useDigest } from "../../src/api/hooks";
import { ApiError } from "../../src/api/client";
import { Banner, Card, Field, GhostButton, PrimaryButton, SectionLabel } from "../../src/components/Primitives";
import { Receipt } from "../../src/components/Receipt";
import { reconcile } from "../../src/notifications";
import { stripMarkdown } from "../../src/utils/text";
import { useTheme, spacing, radius } from "../../src/theme";
import type { CaptureResponse } from "../../src/api/types";

type ReceiptEntry = { id: string; text: string; result: CaptureResponse };

export default function CaptureScreen() {
  const t = useTheme();
  const { data: dash, refetch, isRefetching } = useDashboard();
  const capture = useCapture();
  const morning = useDigest("morning");
  const insights = useDigest("ondemand");

  const [text, setText] = useState("");
  const [receipts, setReceipts] = useState<ReceiptEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [digest, setDigest] = useState<{ title: string; text: string } | null>(null);

  useEffect(() => {
    if (dash?.reminders?.length) reconcile(dash.reminders);
  }, [dash?.reminders]);

  const submit = () => {
    const value = text.trim();
    if (!value) return;
    setError(null);
    capture.mutate(value, {
      onSuccess: (result) => {
        setReceipts((prev) => [{ id: `${Date.now()}`, text: value, result }, ...prev]);
        setText("");
      },
      onError: (e) => setError(e instanceof ApiError ? e.message : "Couldn't log that — try again."),
    });
  };

  const openDigest = (kind: "morning" | "ondemand") => {
    const mutation = kind === "morning" ? morning : insights;
    mutation.mutate(false, {
      onSuccess: (d) => setDigest({ title: kind === "morning" ? "☀️ Morning briefing" : "💡 Insights", text: stripMarkdown(d.text) }),
      onError: (e) => setError(e instanceof ApiError ? e.message : "Couldn't generate that right now."),
    });
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: t.bg }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <FlatList
        data={receipts}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={t.accent} />}
        renderItem={({ item }) => <Receipt text={item.text} result={item.result} />}
        ListHeaderComponent={
          <View>
            {dash?.alerts.map((a, i) => <Banner key={i} text={a} />)}
            {error && <Banner text={error} tone="danger" />}

            <Card style={{ marginBottom: spacing.md }}>
              <SectionLabel>Tell me about your day</SectionLabel>
              <Field label="" value={text} onChangeText={setText} placeholder="ran 5k, remind me to call mom at 6pm…"
                     multiline numberOfLines={3} style={{ minHeight: 72, textAlignVertical: "top" }} />
              <PrimaryButton title={capture.isPending ? "Logging…" : "Log it"} onPress={submit}
                              disabled={!text.trim()} loading={capture.isPending} />
            </Card>

            <View style={{ flexDirection: "row", marginBottom: spacing.lg, gap: spacing.sm }}>
              <View style={{ flex: 1 }}>
                <GhostButton title="☀️ Briefing" onPress={() => openDigest("morning")} />
              </View>
              <View style={{ flex: 1 }}>
                <GhostButton title="💡 Insights" onPress={() => openDigest("ondemand")} />
              </View>
            </View>

            {digest && (
              <Card style={{ marginBottom: spacing.lg, borderColor: t.accent }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: spacing.sm }}>
                  <Text style={{ color: t.accent, fontWeight: "700" }}>{digest.title}</Text>
                  <Pressable onPress={() => setDigest(null)}><Text style={{ color: t.textMuted }}>✕</Text></Pressable>
                </View>
                <Text style={{ color: t.text, fontSize: 14, lineHeight: 20 }}>{digest.text}</Text>
              </Card>
            )}

            {receipts.length > 0 && <SectionLabel>This session</SectionLabel>}
          </View>
        }
        ListEmptyComponent={
          <Text style={{ color: t.textMuted, fontStyle: "italic" }}>
            Nothing logged yet this session — try the box above.
          </Text>
        }
      />
    </KeyboardAvoidingView>
  );
}
