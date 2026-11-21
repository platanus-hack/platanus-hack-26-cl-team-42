import { Badge, Button, Callout, Flex, Text } from "@radix-ui/themes";
import { ComplementDialog } from "../templates/ComplementDialog";
import { sectionLabel } from "../templates/recordFields";
import type { Report, ReviewItem } from "./api";
import { reviewTone } from "./review";
import type { ReportReview } from "./useReportReview";

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });

export function ReviewHeaderAction({ review, busy }: { review: ReportReview; busy: boolean }) {
  const count = review.pending.length;
  return (
    <Flex direction="column" align="end" gap="1">
      <Flex align="center" gap="3" wrap="wrap">
        {count > 0 && (
          <Text size="2" weight="medium" aria-live="polite">
            {count} {count === 1 ? "punto por revisar" : "puntos por revisar"}
          </Text>
        )}
        {count > 0 ? (
          <Button loading={review.reviewing} disabled={busy} onClick={review.validateAndContinue}>
            {review.current ? "Validar y continuar" : "Ir al siguiente pendiente"}
          </Button>
        ) : (
          <Button color="green" loading={review.saving} disabled={busy} onClick={review.save}>
            Guardar informe
          </Button>
        )}
      </Flex>
      {count === 0 && (
        <Text size="1" color="gray" align="right">
          Sin puntos por revisar. Guardar lo publica al equipo del paciente y lo cierra: ya no se podrá editar.
        </Text>
      )}
      {review.error && (
        <Text size="1" color="red" align="right" role="alert">
          {review.error}
        </Text>
      )}
    </Flex>
  );
}

/** El selector conserva los temas del informe y destaca los que tienen puntos pendientes. */
export function ReviewTopicPicker({ topics, review }: { topics: Report["topics"]; review: ReportReview }) {
  return (
    <Flex gap="2" wrap="wrap" role="group" aria-label="Temas del informe">
      {topics.map((topic) => {
        const items = review.pending.filter((item) => topic.sections.includes(item.section));
        const high = items.some((item) => reviewTone(item).color === "red");
        const active = topic.id === review.activeTopicId;
        const label = high ? "Alerta" : items.length > 0 ? "Por revisar" : undefined;
        const color = active ? "indigo" : high ? "red" : label ? "amber" : "gray";

        return (
          <Badge key={topic.id} asChild color={color} variant={active ? "solid" : "soft"}>
            <button
              type="button"
              aria-pressed={active}
              disabled={review.reviewing}
              onClick={() => review.selectTopic(topic.id)}
              style={{ border: 0, cursor: review.reviewing ? "default" : "pointer" }}
            >
              {topic.label}{label && ` · ${label}`}
            </button>
          </Badge>
        );
      })}
    </Flex>
  );
}

/** La alerta se lee junto al contenido del tema seleccionado. */
export function ReviewPointCallout({ report, item, busy }: { report: Report; item: ReviewItem; busy: boolean }) {
  const tone = reviewTone(item);
  const section = sectionLabel(item.section);
  return (
    <Callout.Root size="1" color={tone.color} role="region" aria-label="Punto por revisar">
      <Flex direction="column" gap="2">
        <Callout.Text>
          <strong>{tone.label}</strong> · {section}
        </Callout.Text>
        <Callout.Text>{item.message}</Callout.Text>
        {item.fromEarlierVersion && (
          <Callout.Text>Observación generada antes de la edición. Contrástala con el contenido actualizado.</Callout.Text>
        )}
        <Flex align="center" gap="2" wrap="wrap">
          {item.evidenceTitle && (
            <Text size="1">
              {item.evidenceTitle}
              {item.evidenceTakenAt && ` · ${DATE_FORMAT.format(new Date(item.evidenceTakenAt))}`}
            </Text>
          )}
          <ComplementDialog
            extractionId={report.extractionId}
            section={item.section}
            label={section}
            disabled={busy}
            triggerLabel="Corregir sección"
          />
        </Flex>
      </Flex>
    </Callout.Root>
  );
}
