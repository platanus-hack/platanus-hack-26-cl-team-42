import { createFileRoute } from "@tanstack/react-router";
import { OfficialFormPage } from "../../modules/official-form/OfficialFormPage";

export const Route = createFileRoute("/_authenticated/official-form")({
  component: OfficialFormPage,
});
