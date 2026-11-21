import { createFileRoute } from "@tanstack/react-router";
import { TranscriptionPage } from "../../modules/transcription/TranscriptionPage";

export interface TranscriptionSearch {
  /** Dictado recién guardado que se debe mostrar seleccionado. */
  recording?: string;
}

export const Route = createFileRoute("/_authenticated/transcription")({
  validateSearch: (search: Record<string, unknown>): TranscriptionSearch =>
    typeof search.recording === "string" ? { recording: search.recording } : {},
  component: TranscriptionRoute,
});

function TranscriptionRoute() {
  const { recording } = Route.useSearch();
  return <TranscriptionPage recordingId={recording} />;
}
