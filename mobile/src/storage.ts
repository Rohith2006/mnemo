// expo-secure-store has no web implementation, so route through it only on
// native and fall back to AsyncStorage on web (fine for a LAN dev tool — not
// used for anything more sensitive than a bearer token + a server URL).
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import AsyncStorage from "@react-native-async-storage/async-storage";

export async function getItem(key: string): Promise<string | null> {
  return Platform.OS === "web" ? AsyncStorage.getItem(key) : SecureStore.getItemAsync(key);
}

export async function setItem(key: string, value: string): Promise<void> {
  if (Platform.OS === "web") {
    await AsyncStorage.setItem(key, value);
  } else {
    await SecureStore.setItemAsync(key, value);
  }
}

export async function removeItem(key: string): Promise<void> {
  if (Platform.OS === "web") {
    await AsyncStorage.removeItem(key);
  } else {
    await SecureStore.deleteItemAsync(key);
  }
}
