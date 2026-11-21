import { createFileRoute } from "@tanstack/react-router";
import { RecordingsPage } from "../../modules/recordings/RecordingsPage";

export const Route = createFileRoute("/_authenticated/recordings")({
  component: RecordingsPage,
});
