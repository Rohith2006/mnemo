import React, { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { Link } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import { ApiError } from "../../src/api/client";
import { Field, PrimaryButton, Banner } from "../../src/components/Primitives";
import { useTheme, spacing } from "../../src/theme";

export default function Login() {
  const { serverUrl, configureServer, login } = useAuth();
  const t = useTheme();
  const [url, setUrl] = useState(serverUrl ?? "http://127.0.0.1:8000");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async () => {
    setError(null);
    setLoading(true);
    try {
      await configureServer(url, false); // try it first, don't remember a broken address
      await login(email.trim(), password);
      await configureServer(url, true); // worked — now remember it
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: t.bg }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: "center", padding: spacing.xl }}>
        <Text style={{ fontSize: 28, fontWeight: "800", color: t.text, marginBottom: spacing.xs }}>mnemo</Text>
        <Text style={{ color: t.textMuted, marginBottom: spacing.xl }}>Welcome back.</Text>

        {error && <Banner text={error} tone="danger" />}

        <Field label="Server URL (on your laptop's LAN)" value={url} onChangeText={setUrl}
               autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="http://192.168.1.42:8000" />
        <Field label="Email" value={email} onChangeText={setEmail}
               autoCapitalize="none" autoCorrect={false} keyboardType="email-address" placeholder="you@example.com" />
        <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry placeholder="••••••••" />

        <View style={{ height: spacing.sm }} />
        <PrimaryButton title="Log in" onPress={onSubmit} loading={loading}
                        disabled={!url || !email || !password} />

        <View style={{ flexDirection: "row", justifyContent: "center", marginTop: spacing.lg }}>
          <Text style={{ color: t.textMuted }}>New here? </Text>
          <Link href="/(auth)/signup"><Text style={{ color: t.accent, fontWeight: "700" }}>Create an account</Text></Link>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
