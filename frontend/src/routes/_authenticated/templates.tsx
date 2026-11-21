import { createFileRoute } from "@tanstack/react-router";
import { TemplatesPage } from "../../modules/templates/TemplatesPage";

export const Route = createFileRoute("/_authenticated/templates")({
  component: TemplatesPage,
});
