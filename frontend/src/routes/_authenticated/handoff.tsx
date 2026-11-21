import { createFileRoute } from "@tanstack/react-router";
import { HandoffPage } from "../../modules/handoff/HandoffPage";

export const Route = createFileRoute("/_authenticated/handoff")({
  component: HandoffPage,
});
