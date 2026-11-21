import { useState } from "react";
import { Badge, Button, Callout, Card, Flex, Grid, Heading, Spinner, Text, TextArea } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { formatDuration } from "../recordings/recorderFormat";
import {
  isInProgress,
  recordingAudioUrl,
  useRetryTranscription,
  useTranscripts,
  type Transcript,
  type TranscriptStatus,
} from "./api";

interface TranscriptionPageProps {
  /** Dictado a mostrar seleccionado al llegar desde el grabador. */
  recordingId?: string;
}

export function TranscriptionPage({ recordingId }: TranscriptionPageProps) {
  const { data: transcripts = [], isPending, isError, error } = useTranscripts();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected =
    transcripts.find((transcript) => transcript.id === selectedId) ??
    transcripts.find((transcript) => transcript.recordingId === recordingId) ??
    transcripts[0];

  return (
    <ModulePage stepId="transcription" connected>
      <Grid columns={{ initial: "1", md: "280px 1fr" }} gap="4">
        <Flex direction="column" gap="3">
          <Heading size="4">Dictados</Heading>
          {isError ? (
            <Callout.Root color="red">
              <Callout.Text>No se pudieron cargar las transcripciones: {error.message}</Callout.Text>
            </Callout.Root>
          ) : !isPending && transcripts.length === 0 ? (
            <EmptyState
              title="Sin transcripciones"
              description="Cada dictado que grabes o subas se transcribirá automáticamente y aparecerá aquí."
            />
          ) : (
            transcripts.map((transcript) => (
              <Button
                key={transcript.id}
                variant={transcript.id === selected?.id ? "solid" : "soft"}
                onClick={() => setSelectedId(transcript.id)}
                style={{ justifyContent: "space-between", height: "auto", padding: "8px 12px" }}
              >
                <Flex direction="column" align="start">
                  <span>{transcript.name}</span>
                  <Text size="1">{DATE_FORMAT.format(new Date(transcript.recordedAt))}</Text>
                </Flex>
                <StatusBadge status={transcript.status} />
              </Button>
            ))
          )}
          <Link to="/recordings" style={{ textDecoration: "none" }}>
            <Button variant="ghost" color="gray" size="2">
              Grabar otro dictado
            </Button>
          </Link>
        </Flex>

        <Card>{selected ? <TranscriptDetail transcript={selected} /> : <EmptyDetail />}</Card>
      </Grid>
    </ModulePage>
  );
}

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });

const STATUS_LABELS: Record<TranscriptStatus, { label: string; color: "gray" | "blue" | "green" | "red" }> = {
  pending: { label: "En cola", color: "gray" },
  processing: { label: "Transcribiendo", color: "blue" },
  done: { label: "Transcrito", color: "green" },
  failed: { label: "Error", color: "red" },
};

function StatusBadge({ status }: { status: TranscriptStatus }) {
  const { label, color } = STATUS_LABELS[status];
  return (
    <Badge color={color} variant="surface" radius="full">
      {label}
    </Badge>
  );
}

function TranscriptDetail({ transcript }: { transcript: Transcript }) {
  return (
    <Flex direction="column" gap="3">
      <Flex justify="between" align="center" gap="3" wrap="wrap">
        <Flex direction="column">
          <Heading size="4">{transcript.name}</Heading>
          <Text size="1" color="gray">
            {DATE_FORMAT.format(new Date(transcript.recordedAt))} · {formatDuration(transcript.durationSeconds)} · Español
          </Text>
        </Flex>
        <StatusBadge status={transcript.status} />
      </Flex>

      <audio controls preload="none" src={recordingAudioUrl(transcript)} style={{ width: "100%", height: 36 }} />

      {isInProgress(transcript) ? (
        <Flex align="center" justify="center" gap="3" py="9">
          <Spinner size="3" />
          <Text color="gray">
            {transcript.status === "pending"
              ? "El dictado está en cola para transcribirse…"
              : "Transcribiendo el dictado… puede tardar unos segundos por minuto de audio."}
          </Text>
        </Flex>
      ) : transcript.status === "failed" ? (
        <FailedTranscript transcript={transcript} />
      ) : (
        <TextArea size="3" rows={14} readOnly value={transcript.text} />
      )}
    </Flex>
  );
}

function FailedTranscript({ transcript }: { transcript: Transcript }) {
  const retry = useRetryTranscription();
  return (
    <Callout.Root color="red">
      <Flex direction="column" gap="2">
        <Callout.Text>{transcript.error || "No se pudo transcribir el dictado."}</Callout.Text>
        {retry.isError && <Callout.Text>No se pudo reintentar: {retry.error.message}</Callout.Text>}
        <Flex>
          <Button size="1" color="red" variant="soft" loading={retry.isPending} onClick={() => retry.mutate(transcript.recordingId)}>
            Reintentar
          </Button>
        </Flex>
      </Flex>
    </Callout.Root>
  );
}

function EmptyDetail() {
  return (
    <TextArea
      size="3"
      rows={14}
      disabled
      placeholder="La transcripción del dictado seleccionado aparecerá aquí."
    />
  );
}
