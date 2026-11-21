import { createFileRoute } from "@tanstack/react-router";
import { ConceptsPage } from "../../modules/concepts/ConceptsPage";

export const Route = createFileRoute("/_authenticated/concepts")({
  component: ConceptsPage,
});
