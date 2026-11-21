import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Callout, Card, Flex, Heading, Progress, Select, Spinner, Text } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { professionLabel } from "../recordings/professions";
import { HomologationChip, ReportView } from "../reports/ReportView";
import { ApiError } from "../../services/api/client";
import { useReport, type Homologation, type Report } from "../reports/api";
import { sectionLabel, countFields } from "../templates/recordFields";
import { useExtractRecord, useReportTemplates, useTemplate } from "../templates/api";
import { useRetryTranscription } from "../transcription/api";
import { pipelineKeys, usePipeline } from "./api";
import { useReveal } from "./useReveal";

const STAGES = ["Transcripción", "Parseo a plantilla", "Homologación de conceptos", "Validación del informe"] as const;
const TEMPLATE_WAIT_MS = 12000;

/** Sigue un dictado recién guardado: se transcribe, se parsea, se homologa y termina en su informe. */
export function PipelineView({ recordingId, onMissing }: { recordingId: string; onMissing: () => void }) {
  const { data: pipeline, isError, error } = usePipeline(recordingId);
  const missing = error instanceof ApiError && error.status === 404;
  // Etapas ya desbloqueadas: cada una espera a que la anterior termine de mostrarse.
  const [reached, setReached] = useState(1);
  const container = useRef<HTMLDivElement>(null);
  const advance = (stage: number) => setReached((current) => Math.max(current, stage + 2));

  useEffect(() => {
    container.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [recordingId]);

  // Un dictado que ya no existe (enlace viejo o borrado): se limpia la dirección en vez de mostrar un error.
  useEffect(() => {
    if (missing) onMissing();
  }, [missing, onMissing]);

  if (missing) return null;

  if (isError) {
    return (
      <Callout.Root color="red">
        <Callout.Text>No se pudo consultar el avance: {error.message}</Callout.Text>
      </Callout.Root>
    );
  }

  return (
    <Flex ref={container} direction="column" gap="3" style={{ scrollMarginTop: 16 }}>
      <Heading size="4">Procesando el dictado</Heading>

      <StageCard index={0} reached={reached} title={STAGES[0]}>
        <TranscriptionStage pipeline={pipeline} onFinished={() => advance(0)} />
      </StageCard>
      <StageCard index={1} reached={reached} title={STAGES[1]}>
        <ParsingStage pipeline={pipeline} onFinished={() => advance(1)} />
      </StageCard>
      <StageCard index={2} reached={reached} title={STAGES[2]}>
        <HomologationStage pipeline={pipeline} onFinished={() => advance(2)} />
      </StageCard>
      <StageCard index={3} reached={reached} title={STAGES[3]}>
        {pipeline?.report && (pipeline.report.status === "review" || pipeline.report.status === "done") ? (
          <ReportReview initial={pipeline.report} />
        ) : (
          <WaitingLine text="Preparando el informe para su validación…" />
        )}
      </StageCard>
    </Flex>
  );
}

type PipelineData = ReturnType<typeof usePipeline>["data"];

interface StageProps {
  pipeline: PipelineData;
  onFinished: () => void;
}

function StageCard({ index, reached, title, children }: { index: number; reached: number; title: string; children: ReactNode }) {
  const active = index < reached;
  return (
    <Card style={{ opacity: active ? 1 : 0.55 }}>
      <Flex direction="column" gap="3">
        <Flex align="center" gap="2">
          <Badge color={active ? "indigo" : "gray"} variant="solid" radius="full">
            {index + 1}
          </Badge>
          <Text weight="medium">{title}</Text>
        </Flex>
        {active ? children : <Text size="2" color="gray">En espera…</Text>}
      </Flex>
    </Card>
  );
}

function WaitingLine({ text }: { text: string }) {
  return (
    <Flex align="center" gap="3" py="2">
      <Spinner size="2" />
      <Text size="2" color="gray">
        {text}
      </Text>
    </Flex>
  );
}

function TranscriptionStage({ pipeline, onFinished }: StageProps) {
  const transcript = pipeline?.transcription;
  const retry = useRetryTranscription();
  const queryClient = useQueryClient();
  const text = transcript?.status === "done" ? transcript.text : "";
  // El texto aparece rápido (~2 s como máximo) aunque el backend lo tenga entero.
  const step = Math.max(2, Math.ceil(text.length / 30));
  const shown = useReveal(Math.ceil(text.length / step), 50, text.length > 0) * step;
  const finished = text.length > 0 && shown >= text.length;

  useEffect(() => {
    if (finished) onFinished();
  }, [finished, onFinished]);

  if (transcript?.status === "failed") {
    return (
      <Callout.Root color="red">
        <Flex direction="column" gap="2">
          <Callout.Text>{transcript.error || "No se pudo transcribir el dictado."}</Callout.Text>
          <Flex>
            <Button size="1" color="red" variant="soft" loading={retry.isPending} onClick={() =>
                retry.mutate(transcript.recordingId, {
                  onSuccess: () => queryClient.invalidateQueries({ queryKey: pipelineKeys }),
                })
              }>
              Reintentar
            </Button>
          </Flex>
        </Flex>
      </Callout.Root>
    );
  }
  if (!text) return <WaitingLine text="Transcribiendo el audio…" />;
  return (
    <Text size="2" style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
      {text.slice(0, shown)}
      {!finished && <span aria-hidden="true">▍</span>}
    </Text>
  );
}

function ParsingStage({ pipeline, onFinished }: StageProps) {
  const extraction = pipeline?.extraction;
  const transcript = pipeline?.transcription;
  const retryExtraction = useExtractRecord();
  const queryClient = useQueryClient();
  const { data: template } = useTemplate(extraction?.templateSlug);
  const data = extraction?.data ?? {};
  const sections = template?.output_schema.required ?? Object.keys(data);
  const filled = sections.filter((key) => key in data && countFields(data[key]).filled > 0);
  const extractionDone = extraction?.status === "done";
  // Las secciones se van marcando una a una, con o sin streaming del modelo.
  const revealed = useReveal(extractionDone ? sections.length : filled.length, 100, extraction !== null && extraction !== undefined);
  const finished = extractionDone && sections.length > 0 && revealed >= sections.length;

  useEffect(() => {
    if (finished) onFinished();
  }, [finished, onFinished]);

  if (extraction?.status === "failed") {
    return (
      <Callout.Root color="red">
        <Flex direction="column" gap="2">
          <Callout.Text>{extraction.error || "No se pudo parsear el dictado."}</Callout.Text>
          <Flex>
            <Button
              size="1"
              color="red"
              variant="soft"
              loading={retryExtraction.isPending}
              onClick={() =>
                retryExtraction.mutate(
                  { transcriptId: extraction.transcriptId, templateSlug: extraction.templateSlug },
                  { onSuccess: () => queryClient.invalidateQueries({ queryKey: pipelineKeys }) },
                )
              }
            >
              Reintentar
            </Button>
          </Flex>
        </Flex>
      </Callout.Root>
    );
  }
  if (!extraction) {
    return transcript?.status === "done" ? (
      <TemplateIdentification transcriptId={transcript.id} />
    ) : (
      <Text size="2" color="gray">
        En cuanto haya texto se identifica la plantilla del profesional.
      </Text>
    );
  }
  return (
    <Flex direction="column" gap="2">
      <Flex align="center" gap="2" wrap="wrap">
        {!finished && <Spinner size="2" />}
        <Text size="2">
          Plantilla: <strong>{extraction.templateName}</strong>
        </Text>
        {transcript?.profession && (
          <Badge variant="soft" color="gray">
            {professionLabel(transcript.profession)}
          </Badge>
        )}
      </Flex>
      <Progress value={revealed} max={Math.max(sections.length, 1)} />
      <Flex direction="column" gap="1">
        {sections.slice(0, revealed).map((key) => {
          const { filled: fields } = countFields(data[key]);
          return (
            <Flex key={key} justify="between" gap="3">
              <Text size="2">{sectionLabel(key)}</Text>
              <Text size="1" color={fields > 0 ? "green" : "gray"}>
                {fields > 0 ? `${fields} ${fields === 1 ? "dato" : "datos"}` : "Sin información"}
              </Text>
            </Flex>
          );
        })}
      </Flex>
    </Flex>
  );
}

/** Mientras se deduce la plantilla; si no se logra, se puede elegir a mano. */
function TemplateIdentification({ transcriptId }: { transcriptId: string }) {
  const { data: templates = [] } = useReportTemplates();
  const extract = useExtractRecord();
  const [late, setLate] = useState(false);
  const [slug, setSlug] = useState<string>();

  useEffect(() => {
    const timer = setTimeout(() => setLate(true), TEMPLATE_WAIT_MS);
    return () => clearTimeout(timer);
  }, []);

  if (!late) return <WaitingLine text="Identificando la plantilla según lo dictado…" />;
  return (
    <Callout.Root color="amber">
      <Flex direction="column" gap="2">
        <Callout.Text>No se pudo identificar la plantilla automáticamente. Elígela para continuar.</Callout.Text>
        <Flex gap="2" wrap="wrap">
          <Select.Root value={slug} onValueChange={setSlug}>
            <Select.Trigger placeholder="Elige una plantilla" />
            <Select.Content>
              {templates.map((template) => (
                <Select.Item key={template.slug} value={template.slug}>
                  {template.name}
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
          <Button disabled={!slug} loading={extract.isPending} onClick={() => extract.mutate({ transcriptId, templateSlug: slug })}>
            Parsear
          </Button>
        </Flex>
      </Flex>
    </Callout.Root>
  );
}

function HomologationStage({ pipeline, onFinished }: StageProps) {
  const report = pipeline?.report;
  const entries: Homologation[] = report?.homologations ?? [];
  const changed = entries.filter((entry) => entry.changed);
  const reportDone = report?.status === "review" || report?.status === "done";
  // Cada término se unifica a la vista, uno tras otro.
  const revealed = useReveal(entries.length, 70, report !== null && report !== undefined);
  const finished = reportDone && revealed >= entries.length;

  useEffect(() => {
    if (finished) onFinished();
  }, [finished, onFinished]);

  if (report?.status === "failed") {
    return (
      <Callout.Root color="red">
        <Callout.Text>{report.error || "No se pudo homologar el registro."}</Callout.Text>
      </Callout.Root>
    );
  }
  if (!report) return <WaitingLine text="Esperando el registro parseado…" />;

  const visibleChanged = entries.slice(0, revealed).filter((entry) => entry.changed);
  return (
    <Flex direction="column" gap="2">
      <Flex align="center" gap="2">
        {!finished && <Spinner size="2" />}
        <Text size="2">
          {finished
            ? `${changed.length} ${changed.length === 1 ? "término unificado" : "términos unificados"}; ${entries.length - changed.length} ya usaban el concepto común.`
            : `Unificando términos… ${revealed} de ${entries.length || "?"}`}
        </Text>
      </Flex>
      <Flex gap="2" wrap="wrap">
        {visibleChanged.map((entry, index) => (
          <HomologationChip key={`${entry.path}-${index}`} item={entry} />
        ))}
      </Flex>
    </Flex>
  );
}

/** Revisión del informe recién generado: lo pendiente, completarlo y validarlo (sigue en vivo). */
function ReportReview({ initial }: { initial: Report }) {
  const { data } = useReport(initial.id, initial);
  const report = data ?? initial;
  return (
    <Flex direction="column" gap="3">
      <ReportView report={report} />
      <Flex>
        <Link
          to="/"
          search={{ patient: report.patient ? String(report.patient.id) : undefined, report: report.id }}
        >
          <Button variant="soft">Abrir en Mis pacientes</Button>
        </Link>
      </Flex>
    </Flex>
  );
}
