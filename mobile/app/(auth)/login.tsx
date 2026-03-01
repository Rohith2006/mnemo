import React, { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, View } from "react-native";
import { Link } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import { ApiError } from "../../src/api/client";
import { Button } from "../../src/components/Button";
import { MnemoMark } from "../../src/components/Logo";
import { Screen } from "../../src/components/Screen";
import { Callout, Field } from "../../src/components/Surfaces";
import { Text } from "../../src/components/Text";
import { space, useTheme } from "../../src/theme";

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
      await configureServer(url, true); // worked, now remember it
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Screen>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView
          contentContainerStyle={{
            flexGrow: 1,
            justifyContent: "center",
            padding: space.xxl,
            maxWidth: 460,
            width: "100%",
            alignSelf: "center",
          }}
          keyboardShouldPersistTaps="handled"
        >
          <View style={{ marginBottom: space.xxxl }}>
            <MnemoMark size={30} />
            <Text variant="display" style={{ marginTop: space.lg }}>
              Welcome back
            </Text>
            <Text variant="callout" tone="muted" style={{ marginTop: space.xs }}>
              Pick up where your memory left off.
            </Text>
          </View>

          {!!error && <Callout text={error} tone="critical" />}

          <Field
            label="Server"
            hint="Your mnemo backend on the local network."
            value={url}
            onChangeText={setUrl}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            placeholder="http://192.168.1.42:8000"
          />
          <Field
            label="Email"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            textContentType="emailAddress"
            placeholder="you@example.com"
          />
          <Field
            label="Password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            textContentType="password"
            placeholder="Your password"
          />

          <Button
            title="Log in"
            full
            onPress={onSubmit}
            loading={loading}
            disabled={!url || !email || !password}
            style={{ marginTop: space.sm }}
          />

          <View
            style={{
              flexDirection: "row",
              justifyContent: "center",
              alignItems: "center",
              gap: space.xs,
              marginTop: space.xxl,
            }}
          >
            <Text variant="footnote" tone="muted">
              New here?
            </Text>
            <Link href="/(auth)/signup" accessibilityRole="link">
              <Text variant="footnote" color={t.ink} style={{ textDecorationLine: "underline" }}>
                Create an account
              </Text>
            </Link>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}
