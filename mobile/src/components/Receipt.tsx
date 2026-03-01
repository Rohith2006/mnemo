import React, { useEffect, useRef } from "react";
import { AccessibilityInfo, Animated, Platform, View } from "react-native";
import type { CaptureResponse } from "../api/types";
import { Card } from "./Surfaces";
import { Text } from "./Text";
import { Icon, IconName } from "./Icon";
import { duration, iconSize, space, useTheme } from "../theme";

/**
 * The signature surface. A capture is not answered, it is recorded, so this
 * reads as a ledger entry: a monospace time rail against a hairline rule, the
 * raw words at the top, then one typed line per thing mnemo took from them.
 */

type Line = { icon: IconName; label: string; value?: string; tone?: "positive" | "caution" | "muted" };

function toLines(result: CaptureResponse): Line[] {
  const lines: Line[] = [];

  for (const f of result.facts) lines.push({ icon: "fact", label: f });
  for (const f of result.facts_updated ?? []) lines.push({ icon: "factUpdated", label: f, value: "updated" });
  for (const f of result.facts_removed ?? []) lines.push({ icon: "factRemoved", label: f, value: "removed" });

  for (const e of result.log) {
    const value = e.value != null ? `${e.value}${e.unit ? " " + e.unit : ""}` : undefined;
    lines.push({ icon: "metric", label: e.key, value });
  }

  for (const task of result.tasks) {
    lines.push({ icon: "task", label: task.task, value: task.due ? shortDate(task.due) : "open" });
  }

  for (const d of result.done) {
    lines.push({ icon: "taskDone", label: d.task, value: "done", tone: "positive" });
  }

  for (const h of result.habits) {
    lines.push({ icon: "habit", label: h.name, value: `${h.streak}d`, tone: "positive" });
  }

  if (result.mood) {
    lines.push({
      icon: "mood",
      label: result.mood.note || "Mood",
      value: `${result.mood.mood}/10`,
    });
  }

  if (result.reminder) {
    lines.push({
      icon: "reminder",
      label: result.reminder.task,
      value: shortTime(result.reminder.fire_at),
      tone: "caution",
    });
  }

  return lines;
}

function shortTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function shortDate(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function Receipt({ text, at, result }: { text: string; at: number; result: CaptureResponse }) {
  const t = useTheme();
  const lines = toLines(result);
  const enter = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    let cancelled = false;
    AccessibilityInfo.isReduceMotionEnabled().then((reduced) => {
      if (cancelled) return;
      if (reduced) {
        enter.setValue(1);
        return;
      }
      Animated.timing(enter, {
        toValue: 1,
        duration: duration.enter,
        useNativeDriver: Platform.OS !== "web",
      }).start();
    });
    return () => {
      cancelled = true;
    };
  }, [enter]);

  const tones = { positive: t.positive, caution: t.caution, muted: t.inkMuted };

  return (
    <Animated.View
      style={{
        opacity: enter,
        transform: [{ translateY: enter.interpolate({ inputRange: [0, 1], outputRange: [8, 0] }) }],
        marginBottom: space.md,
      }}
    >
      <Card style={{ flexDirection: "row", padding: space.lg, gap: space.lg }}>
        {/* Fixed width so every row in the list aligns to the same rule.
            Sized for a 12-hour clock, which is the longest form it can take. */}
        <View style={{ width: 56 }}>
          <Text variant="monoSmall" tone="faint" numberOfLines={1}>
            {shortTime(new Date(at).toISOString())}
          </Text>
        </View>

        <View style={{ width: 1, backgroundColor: t.hairline }} />

        <View style={{ flex: 1, gap: space.sm }}>
          <Text variant="footnote" tone="muted" style={{ fontStyle: "italic" }}>
            {text}
          </Text>

          {lines.length === 0 ? (
            <Text variant="callout" tone="faint">
              Noted. Nothing to track in that one.
            </Text>
          ) : (
            lines.map((line, i) => (
              <View key={i} style={{ flexDirection: "row", alignItems: "flex-start", gap: space.sm }}>
                <View style={{ paddingTop: 3 }}>
                  <Icon
                    name={line.icon}
                    size={iconSize.sm}
                    color={line.tone ? tones[line.tone] : t.inkFaint}
                  />
                </View>
                <Text variant="callout" style={{ flex: 1 }}>
                  {line.label}
                </Text>
                {!!line.value && (
                  <Text variant="mono" tone={line.tone === "positive" ? "positive" : "muted"}>
                    {line.value}
                  </Text>
                )}
              </View>
            ))
          )}
        </View>
      </Card>
    </Animated.View>
  );
}
