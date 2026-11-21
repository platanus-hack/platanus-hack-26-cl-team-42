import { createFileRoute } from "@tanstack/react-router";
import { ConsolidationPage } from "../../modules/consolidation/ConsolidationPage";

export const Route = createFileRoute("/_authenticated/consolidation")({
  component: ConsolidationPage,
});
