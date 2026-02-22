import React from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useDashboard, useCompleteTask, useCancelReminder, useLogHabit } from "../../src/api/hooks";
import { Card, EmptyState, Pill, SectionLabel } from "../../src/components/Primitives";
import { useTheme, spacing } from "../../src/theme";

export default function TrackScreen() {
  const t = useTheme();
  const { data: dash, refetch, isRefetching } = useDashboard();
  const completeTask = useCompleteTask();
  const cancelReminder = useCancelReminder();
  const logHabit = useLogHabit();

  return (
    <ScrollView style={{ flex: 1, backgroundColor: t.bg }} contentContainerStyle={{ padding: spacing.lg }}
      refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={t.accent} />}>

      <SectionLabel>Profile</SectionLabel>
      <View style={{ flexDirection: "row", flexWrap: "wrap", marginBottom: spacing.lg }}>
        {dash?.profile.length ? dash.profile.map((f, i) => <Pill key={i}>{f}</Pill>) : <EmptyState>Nothing yet</EmptyState>}
      </View>

      <SectionLabel>🔥 Habits</SectionLabel>
      <Card style={{ marginBottom: spacing.lg }}>
        {dash?.habits.length ? dash.habits.map((h, i) => (
          <Pressable key={h.name} onPress={() => logHabit.mutate(h.name)}
            style={{ flexDirection: "row", justifyContent: "space-between",
              paddingVertical: 8, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: t.border }}>
            <Text style={{ color: t.text, fontSize: 14 }}>{h.name}</Text>
            <Text style={{ color: t.success, fontWeight: "700", fontSize: 14 }}>
              day {h.streak} <Text style={{ color: t.textMuted, fontWeight: "400" }}>/ best {h.best_streak}</Text>
            </Text>
          </Pressable>
        )) : <EmptyState>No habits tracked yet</EmptyState>}
        {!!dash?.habits.length && (
          <Text style={{ color: t.textMuted, fontSize: 11, marginTop: spacing.sm, fontStyle: "italic" }}>
            Tap a habit to log it done today
          </Text>
        )}
      </Card>

      <SectionLabel>✅ Open tasks</SectionLabel>
      <Card style={{ marginBottom: spacing.lg }}>
        {dash?.tasks.length ? dash.tasks.map((task, i) => (
          <Pressable key={task.id} onPress={() => completeTask.mutate(task.id)}
            style={{ flexDirection: "row", alignItems: "center", paddingVertical: 8,
              borderTopWidth: i > 0 ? 1 : 0, borderTopColor: t.border }}>
            <Text style={{ fontSize: 16, marginRight: spacing.sm }}>☐</Text>
            <Text style={{ color: t.text, fontSize: 14, flex: 1 }}>{task.task}</Text>
            {task.due && <Text style={{ color: t.textMuted, fontSize: 12 }}>{task.due.slice(0, 16).replace("T", " ")}</Text>}
          </Pressable>
        )) : <EmptyState>All clear</EmptyState>}
      </Card>

      {!!dash?.trends.length && (
        <>
          <SectionLabel>📈 Trends</SectionLabel>
          <Card style={{ marginBottom: spacing.lg }}>
            {dash.trends.map((tr, i) => (
              <Text key={i} style={{ color: t.textMuted, fontSize: 13, fontFamily: "monospace", marginBottom: 3 }}>{tr}</Text>
            ))}
          </Card>
        </>
      )}

      {dash?.mood && (
        <>
          <SectionLabel>🙂 Mood (7d)</SectionLabel>
          <Card style={{ marginBottom: spacing.lg, flexDirection: "row", alignItems: "baseline" }}>
            <Text style={{ color: t.success, fontSize: 26, fontWeight: "800" }}>{dash.mood.avg}</Text>
            <Text style={{ color: t.textMuted, marginLeft: spacing.sm }}>/10 · {dash.mood.count} entries</Text>
          </Card>
        </>
      )}

      {!!dash?.reminders.length && (
        <>
          <SectionLabel>⏰ Reminders</SectionLabel>
          <Card style={{ marginBottom: spacing.lg }}>
            {dash.reminders.map((r, i) => (
              <Pressable key={r.id} onLongPress={() => cancelReminder.mutate(r.id)}
                style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 8,
                  borderTopWidth: i > 0 ? 1 : 0, borderTopColor: t.border }}>
                <Text style={{ color: t.text, fontSize: 14, flex: 1 }}>{r.task}</Text>
                <Text style={{ color: t.textMuted, fontSize: 12 }}>
                  {new Date(r.fire_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </Text>
              </Pressable>
            ))}
            <Text style={{ color: t.textMuted, fontSize: 11, marginTop: spacing.sm, fontStyle: "italic" }}>
              Long-press a reminder to cancel it
            </Text>
          </Card>
        </>
      )}
    </ScrollView>
  );
}
