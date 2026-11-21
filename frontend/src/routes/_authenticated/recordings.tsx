import { createFileRoute } from "@tanstack/react-router";
import { RecordingsPage } from "../../modules/recordings/RecordingsPage";

export interface RecordingsSearch {
  /** Dictado recién guardado cuyo proceso se muestra. */
  recording?: string;
}

export const Route = createFileRoute("/_authenticated/recordings")({
  validateSearch: (search: Record<string, unknown>): RecordingsSearch =>
    typeof search.recording === "string" ? { recording: search.recording } : {},
  component: RecordingsRoute,
});

function RecordingsRoute() {
  const { recording } = Route.useSearch();
  return <RecordingsPage recordingId={recording} />;
}
