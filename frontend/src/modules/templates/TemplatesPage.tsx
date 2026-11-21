import { useState } from "react";
import { Badge, Button, Callout, Card, Flex, Grid, Heading, Select, Spinner, Text } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { useTranscripts } from "../transcription/api";
import {
  isExtractionInProgress,
  useExtractions,
  useExtractRecord,
  useReportTemplates,
  type Extraction,
  type ExtractionStatus,
  type ReportTemplate,
} from "./api";

export function TemplatesPage() {
  const { data: transcripts = [], isPending } = useTranscripts();
  const { data: templates = [] } = useReportTemplates();
  const { data: extractions = [] } = useExtractions();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const ready = transcripts.filter((transcript) => transcript.status === "done");
  const selected = ready.find((transcript) => transcript.id === selectedId) ?? ready[0];
  const extraction = extractions.find((item) => item.transcriptId === selected?.id);

  return (
    <ModulePage stepId="templates" connected>
      <Grid columns={{ initial: "1", md: "280px 1fr" }} gap="4">
        <Flex direction="column" gap="3">
          <Heading size="4">Transcripciones</Heading>
          {!isPending && ready.length === 0 ? (
            <EmptyState
              title="Sin transcripciones listas"
              description="Cuando un dictado termine de transcribirse podrás estructurarlo con una plantilla."
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
                  Elige la plantilla del profesional y Qwen completará sus campos con el texto transcrito. Revisa los
                  valores antes de continuar.
                </Text>
              </Flex>
              <ExtractControls
                key={selected.id}
                transcriptId={selected.id}
                templates={templates}
                current={extraction}
              />
              {extraction && <ExtractionResult extraction={extraction} />}
            </Flex>
          ) : (
            <Text size="2" color="gray">
              Selecciona una transcripción para estructurarla.
            </Text>
          )}
        </Card>
      </Grid>
    </ModulePage>
  );
}

const STATUS_LABELS: Record<ExtractionStatus, { label: string; color: "gray" | "blue" | "green" | "red" }> = {
  pending: { label: "En cola", color: "gray" },
  processing: { label: "Extrayendo", color: "blue" },
  done: { label: "Estructurado", color: "green" },
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

interface ExtractControlsProps {
  transcriptId: string;
  templates: ReportTemplate[];
  current: Extraction | undefined;
}

function ExtractControls({ transcriptId, templates, current }: ExtractControlsProps) {
  const extract = useExtractRecord();
  const [templateSlug, setTemplateSlug] = useState<string | undefined>(current?.templateSlug);
  const busy = extract.isPending || (current !== undefined && isExtractionInProgress(current));

  return (
    <Flex direction="column" gap="2">
      <Flex gap="3" align="center" wrap="wrap">
        <Select.Root value={templateSlug} onValueChange={setTemplateSlug}>
          <Select.Trigger placeholder="Plantilla" style={{ minWidth: 260 }} />
          <Select.Content>
            {templates.map((template) => (
              <Select.Item key={template.slug} value={template.slug}>
                {template.name}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
        <Button
          disabled={!templateSlug}
          loading={busy}
          onClick={() => templateSlug && extract.mutate({ transcriptId, templateSlug })}
        >
          {current ? "Volver a extraer" : "Extraer registro"}
        </Button>
      </Flex>
      {extract.isError && (
        <Callout.Root color="red">
          <Callout.Text>No se pudo iniciar la extracción: {extract.error.message}</Callout.Text>
        </Callout.Root>
      )}
    </Flex>
  );
}

function ExtractionResult({ extraction }: { extraction: Extraction }) {
  if (isExtractionInProgress(extraction)) {
    return (
      <Flex align="center" justify="center" gap="3" py="6">
        <Spinner size="3" />
        <Text color="gray">Qwen está extrayendo el registro con «{extraction.templateName}»…</Text>
      </Flex>
    );
  }
  if (extraction.status === "failed") {
    return (
      <Callout.Root color="red">
        <Callout.Text>{extraction.error || "No se pudo extraer el registro."}</Callout.Text>
      </Callout.Root>
    );
  }
  return (
    <Flex direction="column" gap="2">
      <Heading size="3">{extraction.templateName}</Heading>
      <RecordValue value={extraction.data} />
    </Flex>
  );
}

function RecordValue({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") {
    return <Text color="gray">—</Text>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <Text color="gray">—</Text>;
    return (
      <Flex direction="column" gap="2">
        {value.map((item, index) => (
          <Card key={index} variant="surface">
            <RecordValue value={item} />
          </Card>
        ))}
      </Flex>
    );
  }
  if (typeof value === "object") {
    return (
      <Flex direction="column" gap="2">
        {Object.entries(value as Record<string, unknown>).map(([key, child]) => (
          <Flex key={key} direction="column" gap="1">
            <Text size="2" weight="medium">
              {labelFor(key)}
            </Text>
            <RecordValue value={child} />
          </Flex>
        ))}
      </Flex>
    );
  }
  return <Text size="2">{String(value)}</Text>;
}

function labelFor(key: string): string {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
