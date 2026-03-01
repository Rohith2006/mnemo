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

export default function Signup() {
  const { serverUrl, configureServer, signup } = useAuth();
  const t = useTheme();
  const [url, setUrl] = useState(serverUrl ?? "http://127.0.0.1:8000");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const shortPassword = password.length > 0 && password.length < 8;

  const onSubmit = async () => {
    setError(null);
    setLoading(true);
    try {
      await configureServer(url, false); // try it first, don't remember a broken address
      await signup(email.trim(), password, name.trim());
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
              Create an account
            </Text>
            <Text variant="callout" tone="muted" style={{ marginTop: space.xs }}>
              Everything you tell mnemo stays on your own server.
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
          <Field label="Name" value={name} onChangeText={setName} placeholder="What should mnemo call you?" />
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
            textContentType="newPassword"
            placeholder="At least 8 characters"
            error={shortPassword ? "Use at least 8 characters." : undefined}
          />

          <Button
            title="Create account"
            full
            onPress={onSubmit}
            loading={loading}
            disabled={!url || !email || password.length < 8}
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
              Already have an account?
            </Text>
            <Link href="/(auth)/login" accessibilityRole="link">
              <Text variant="footnote" color={t.ink} style={{ textDecorationLine: "underline" }}>
                Log in
              </Text>
            </Link>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}
