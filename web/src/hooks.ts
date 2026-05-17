// TanStack Query hooks wrapping the Task-13 api.ts wrappers.
//
// Kept in one module so RTL tests can vi.mock("../hooks") wholesale
// instead of standing up a QueryClientProvider per test.

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  deleteTranscript,
  getMe,
  getTranscript,
  listTranscripts,
} from "./api";

const TRANSCRIPTS_KEY = ["transcripts"] as const;

export function useTranscripts() {
  return useQuery({
    queryKey: TRANSCRIPTS_KEY,
    queryFn: listTranscripts,
  });
}

export function useTranscript(id: string) {
  return useQuery({
    queryKey: ["transcript", id],
    queryFn: () => getTranscript(id),
    enabled: id.length > 0,
  });
}

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: getMe,
  });
}

export function useDeleteTranscript() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteTranscript,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: TRANSCRIPTS_KEY });
    },
  });
}
