import { createFileRoute } from "@tanstack/react-router";
import { TranscriptionPage } from "../../modules/transcription/TranscriptionPage";

export const Route = createFileRoute("/_authenticated/transcription")({
  component: TranscriptionPage,
});
