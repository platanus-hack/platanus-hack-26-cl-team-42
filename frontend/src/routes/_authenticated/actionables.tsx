import { createFileRoute } from "@tanstack/react-router";
import { ActionablesPage } from "../../modules/actionables/ActionablesPage";

export const Route = createFileRoute("/_authenticated/actionables")({
  component: ActionablesPage,
});
