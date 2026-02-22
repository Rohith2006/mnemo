import React from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, TextInputProps, View } from "react-native";
import { useTheme, spacing, radius } from "../theme";

export function Card({ children, style }: { children: React.ReactNode; style?: object }) {
  const t = useTheme();
  return (
    <View style={[{ backgroundColor: t.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: t.border,
                    padding: spacing.lg }, style]}>
      {children}
    </View>
  );
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  const t = useTheme();
  return (
    <Text style={{ color: t.textMuted, fontSize: 12, fontWeight: "700", letterSpacing: 0.8,
                    textTransform: "uppercase", marginBottom: spacing.sm }}>
      {children}
    </Text>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  const t = useTheme();
  return <Text style={{ color: t.textMuted, fontStyle: "italic", fontSize: 14 }}>{children}</Text>;
}

export function Pill({ children }: { children: React.ReactNode }) {
  const t = useTheme();
  return (
    <View style={{ backgroundColor: t.surfaceAlt, borderRadius: radius.pill, paddingVertical: spacing.xs,
                    paddingHorizontal: spacing.md, marginRight: spacing.xs, marginBottom: spacing.xs }}>
      <Text style={{ color: t.text, fontSize: 13 }}>{children}</Text>
    </View>
  );
}

export function PrimaryButton({ title, onPress, disabled, loading }:
  { title: string; onPress: () => void; disabled?: boolean; loading?: boolean }) {
  const t = useTheme();
  return (
    <Pressable onPress={onPress} disabled={disabled || loading}
      style={({ pressed }) => [styles.button, { backgroundColor: t.accent, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 }]}>
      {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>{title}</Text>}
    </Pressable>
  );
}

export function GhostButton({ title, onPress, danger }: { title: string; onPress: () => void; danger?: boolean }) {
  const t = useTheme();
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.ghostButton,
      { borderColor: danger ? t.danger : t.border, opacity: pressed ? 0.6 : 1 }]}>
      <Text style={{ color: danger ? t.danger : t.text, fontWeight: "600", fontSize: 14 }}>{title}</Text>
    </Pressable>
  );
}

export function Field(props: TextInputProps & { label: string }) {
  const t = useTheme();
  return (
    <View style={{ marginBottom: spacing.md }}>
      <Text style={{ color: t.textMuted, fontSize: 13, marginBottom: spacing.xs }}>{props.label}</Text>
      <TextInput
        {...props}
        placeholderTextColor={t.textMuted}
        style={[{ backgroundColor: t.surfaceAlt, borderRadius: radius.md, borderWidth: 1, borderColor: t.border,
                  padding: spacing.md, color: t.text, fontSize: 15 }, props.style]}
      />
    </View>
  );
}

export function Banner({ text, tone = "warn" }: { text: string; tone?: "warn" | "danger" }) {
  const t = useTheme();
  const color = tone === "danger" ? t.danger : t.warn;
  return (
    <View style={{ backgroundColor: color + "22", borderColor: color + "55", borderWidth: 1, borderRadius: radius.md,
                    padding: spacing.md, marginBottom: spacing.sm }}>
      <Text style={{ color: t.text, fontSize: 13 }}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  button: { borderRadius: radius.md, paddingVertical: 14, alignItems: "center", justifyContent: "center" },
  buttonText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  ghostButton: { borderRadius: radius.md, borderWidth: 1, paddingVertical: 10, paddingHorizontal: spacing.md,
                 alignItems: "center" },
});
