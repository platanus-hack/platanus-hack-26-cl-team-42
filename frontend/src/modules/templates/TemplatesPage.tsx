import { useEffect, useRef, useState } from "react";
import { Badge, Button, Callout, Card, Flex, Grid, Heading, Select, Spinner, Text } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { professionLabel } from "../recordings/professions";
import { useTranscripts } from "../transcription/api";
import { RecordView } from "./RecordSections";
import {
  isExtractionInProgress,
  useExtractions,
  useExtractRecord,
  useReportTemplates,
  useTemplate,
  type Extraction,
  type ExtractionStatus,
  type ReportTemplate,
  type TemplateDetail,
} from "./api";

export function TemplatesPage() {
  const { data: transcripts = [], isPending } = useTranscripts();
  const { data: templates = [] } = useReportTemplates();
  const { data: extractions = [], isPending: extractionsPending } = useExtractions();
  const { mutate: startExtraction } = useExtractRecord();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const requested = useRef(new Set<string>());

  const ready = transcripts.filter((transcript) => transcript.status === "done");
  const newest = [...ready].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const selected = ready.find((transcript) => transcript.id === selectedId) ?? newest;
  const extraction = extractions.find((item) => item.transcriptId === selected?.id);
  const automaticSlug = templates.find((template) => template.profession === selected?.profession)?.slug;
  const { data: template } = useTemplate(extraction?.templateSlug ?? automaticSlug);

  // Al llegar al paso, el dictado se parsea solo con la plantilla de su tipo de profesional.
  useEffect(() => {
    if (!selected || extractionsPending || extraction || !automaticSlug) return;
    if (requested.current.has(selected.id)) return;
    requested.current.add(selected.id);
    startExtraction({ transcriptId: selected.id });
  }, [selected, extraction, extractionsPending, automaticSlug, startExtraction]);

  return (
    <ModulePage stepId="templates" connected>
      <Grid columns={{ initial: "1", md: "280px 1fr" }} gap="4">
        <Flex direction="column" gap="3">
          <Heading size="4">Transcripciones</Heading>
          {!isPending && ready.length === 0 ? (
            <EmptyState
              title="Sin transcripciones listas"
              description="Cuando un dictado termine de transcribirse se parseará con la plantilla de su profesional."
            />
          ) : (
            ready.map((transcript) => {
              const status = extractions.find((item) => item.transcriptId === transcript.id)?.status;
              return (
                <Button
                  key={transcript.id}
                  variant={transcript.id === selected?.id ? "solid" : "soft"}
                  onClick={() => setSelectedId(transcript.id)}
                  style={{ justifyContent: "space-between", height: "auto", padding: "8px 12px" }}
                >
                  <span>{transcript.name}</span>
                  {status && <ExtractionBadge status={status} />}
                </Button>
              );
            })
          )}
          <Link to="/transcription" style={{ textDecoration: "none" }}>
            <Button variant="ghost" color="gray" size="2">
              Ver transcripciones
            </Button>
          </Link>
        </Flex>

        <Card>
          {selected ? (
            <Flex direction="column" gap="4">
              <Flex direction="column" gap="1">
                <Heading size="4">{selected.name}</Heading>
                <Text size="2" color="gray">
                  {selected.profession
                    ? `Dictado de ${professionLabel(selected.profession)}: la plantilla se elige y se llena automáticamente.`
                    : "Este dictado no indica el tipo de profesional: elige la plantilla manualmente."}
                </Text>
              </Flex>
              <TemplatePicker
                key={selected.id}
                transcriptId={selected.id}
                templates={templates}
                automaticSlug={automaticSlug}
                current={extraction}
              />
              {extraction ? <ExtractionBody extraction={extraction} template={template} /> : null}
            </Flex>
          ) : (
            <Text size="2" color="gray">
              Selecciona una transcripción para parsearla.
            </Text>
          )}
        </Card>
      </Grid>
    </ModulePage>
  );
}

const STATUS_LABELS: Record<ExtractionStatus, { label: string; color: "gray" | "blue" | "green" | "red" }> = {
  pending: { label: "En cola", color: "gray" },
  processing: { label: "Llenando", color: "blue" },
  done: { label: "Parseado", color: "green" },
  failed: { label: "Error", color: "red" },
};

function ExtractionBadge({ status }: { status: ExtractionStatus }) {
  const { label, color } = STATUS_LABELS[status];
  return (
    <Badge color={color} variant="surface" radius="full">
      {label}
    </Badge>
  );
}

interface TemplatePickerProps {
  transcriptId: string;
  templates: ReportTemplate[];
  automaticSlug: string | undefined;
  current: Extraction | undefined;
}

/** La plantilla sale del rol del dictado; este selector solo sirve para cambiarla o elegirla a mano. */
function TemplatePicker({ transcriptId, templates, automaticSlug, current }: TemplatePickerProps) {
  const extract = useExtractRecord();
  const [chosenSlug, setChosenSlug] = useState<string | undefined>();
  const templateSlug = chosenSlug ?? current?.templateSlug ?? automaticSlug;
  const busy = extract.isPending || (current !== undefined && isExtractionInProgress(current));
  const changed = current !== undefined && templateSlug !== current.templateSlug;

  return (
    <Flex direction="column" gap="2">
      <Flex gap="3" align="center" wrap="wrap">
        <Text size="2" weight="medium">
          Plantilla
        </Text>
        <Select.Root value={templateSlug} onValueChange={setChosenSlug}>
          <Select.Trigger placeholder="Elige una plantilla" style={{ minWidth: 260 }} />
          <Select.Content>
            {templates.map((template) => (
              <Select.Item key={template.slug} value={template.slug}>
                {template.name}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
        {(!current || changed || current.status === "failed") && (
          <Button
            disabled={!templateSlug}
            loading={busy}
            onClick={() => templateSlug && extract.mutate({ transcriptId, templateSlug })}
          >
            {current ? "Volver a parsear" : "Parsear"}
          </Button>
        )}
      </Flex>
      {extract.isError && (
        <Callout.Root color="red">
          <Callout.Text>No se pudo iniciar el parseo: {extract.error.message}</Callout.Text>
        </Callout.Root>
      )}
    </Flex>
  );
}

interface ExtractionBodyProps {
  extraction: Extraction;
  template: TemplateDetail | undefined;
}

function ExtractionBody({ extraction, template }: ExtractionBodyProps) {
  if (extraction.status === "failed") {
    return (
      <Callout.Root color="red">
        <Callout.Text>{extraction.error || "No se pudo parsear el dictado."}</Callout.Text>
      </Callout.Root>
    );
  }
  if (extraction.status === "pending") {
    return (
      <Flex align="center" justify="center" gap="3" py="6">
        <Spinner size="3" />
        <Text color="gray">Preparando el parseo con «{extraction.templateName}»…</Text>
      </Flex>
    );
  }
  return <RecordView extraction={extraction} template={template} />;
}
