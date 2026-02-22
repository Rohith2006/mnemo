import React from "react";
import { Text, View } from "react-native";
import type { CaptureResponse } from "../api/types";
import { Card } from "./Primitives";
import { useTheme, spacing } from "../theme";

/** Renders what a capture turned into — a receipt, not a chat reply. */
export function Receipt({ text, result }: { text: string; result: CaptureResponse }) {
  const t = useTheme();
  const lines: string[] = [];
  for (const f of result.facts) lines.push(`📝 ${f}`);
  for (const e of result.log) lines.push(`📈 ${e.key}${e.value != null ? `: ${e.value}${e.unit ? " " + e.unit : ""}` : ""}`);
  for (const task of result.tasks) lines.push(`✅ ${task.task}${task.due ? ` (due ${task.due.slice(0, 16).replace("T", " ")})` : ""}`);
  for (const d of result.done) lines.push(`✔️ Completed: ${d.task}`);
  for (const h of result.habits) lines.push(`🔥 ${h.name} — day ${h.streak}`);
  if (result.mood) lines.push(`🙂 Mood: ${result.mood.mood}/10${result.mood.note ? ` — ${result.mood.note}` : ""}`);
  if (result.reminder) {
    const at = new Date(result.reminder.fire_at);
    lines.push(`⏰ Reminder set: "${result.reminder.task}" at ${at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`);
  }

  return (
    <Card style={{ marginBottom: spacing.md }}>
      <Text style={{ color: t.textMuted, fontSize: 13, marginBottom: spacing.sm }}>“{text}”</Text>
      {lines.length === 0 ? (
        <Text style={{ color: t.text, fontSize: 14 }}>Noted — nothing specific to track from that.</Text>
      ) : (
        lines.map((line, i) => (
          <Text key={i} style={{ color: t.text, fontSize: 14, marginBottom: 3 }}>{line}</Text>
        ))
      )}
    </Card>
  );
}
