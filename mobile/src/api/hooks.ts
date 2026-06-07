import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  CaptureResponse,
  ChatMessageOut,
  ChatResponse,
  ConversationOut,
  DashboardOut,
  DigestOut,
  HabitOut,
  TaskOut,
} from "./types";
import { scheduleReminder, cancelReminder as cancelLocalReminder, cancelAll } from "../notifications";

export function useDashboard() {
  return useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<DashboardOut>("/api/dashboard") });
}

export function useCapture() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => api.post<CaptureResponse>("/api/capture", { text }),
    onSuccess: async (res) => {
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      if (res.reminder) await scheduleReminder(res.reminder);
    },
  });
}

export function useChat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ message, conversationId }: { message: string; conversationId?: string }) =>
      api.post<ChatResponse>("/api/chat", { message, conversation_id: conversationId }),
    onSuccess: async (res) => {
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      // exact: true — otherwise this partial-matches and also invalidates
      // ["conversations", id, "messages"] for whichever thread is currently
      // open, background-refetching it. That refetch would then duplicate
      // the just-sent exchange alongside ChatThread's own optimistic
      // `pending` state (which isn't cleared until the user switches
      // conversations), rendering every sent message twice.
      qc.invalidateQueries({ queryKey: ["conversations"], exact: true });
      if (res.reminder) await scheduleReminder(res.reminder);
    },
  });
}

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: () => api.get<ConversationOut[]>("/api/conversations"),
  });
}

export function useConversationMessages(conversationId: string | null) {
  return useQuery({
    queryKey: ["conversations", conversationId, "messages"],
    queryFn: () => api.get<ChatMessageOut[]>(`/api/conversations/${conversationId}/messages`),
    enabled: !!conversationId,
  });
}

export function useRenameConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      api.patch<ConversationOut>(`/api/conversations/${id}`, { title }),
    // exact: true for the same reason as useChat above — renaming one
    // conversation shouldn't refetch whichever different conversation's
    // thread happens to be open at the time.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"], exact: true }),
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/api/conversations/${id}`),
    // exact: true for the same reason as useChat above — deleting one
    // conversation shouldn't refetch whichever different conversation's
    // thread happens to be open at the time.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"], exact: true }),
  });
}

export function useCompleteTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<TaskOut>(`/api/tasks/${id}/complete`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
}

export function useReopenTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<TaskOut>(`/api/tasks/${id}/reopen`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
}

export function useAddTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (task: string) => api.post<TaskOut[]>("/api/tasks", { task }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
}

export function useLogHabit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.post<HabitOut>(`/api/habits/${encodeURIComponent(name)}/log`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
}

export function useDigest(kind: "morning" | "evening" | "ondemand") {
  const qc = useQueryClient();
  return useMutation<DigestOut, Error, boolean>({
    mutationFn: (refresh) => api.get<DigestOut>(`/api/digests/${kind}${refresh ? "?refresh=true" : ""}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
}

export function useCancelReminder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/api/reminders/${id}`),
    onSuccess: async (_data, id) => {
      await cancelLocalReminder(id);
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useForget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>("/api/forget"),
    onSuccess: async () => {
      await cancelAll(); // the server dropped the reminders; drop their local alarms too
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
