import { useRef, useState, type ChangeEvent } from "react";
import {
  AlertDialog,
  Badge,
  Box,
  Button,
  Callout,
  Card,
  Flex,
  Heading,
  IconButton,
  Spinner,
  Table,
  Text,
  TextArea,
  TextField,
} from "@radix-ui/themes";
import { useNavigate } from "@tanstack/react-router";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { StepIcon } from "../../components/icons";
import { useDeleteRecording, useRecordings, useUploadRecording, type Recording } from "./api";
import { formatBytes, formatDuration } from "./recorderFormat";
import { isRecordingSupported, useAudioRecorder } from "./useAudioRecorder";

export function RecordingsPage() {
  const [patientReference, setPatientReference] = useState("");
  const navigate = useNavigate();
  // Paso 2 del flujo: el dictado guardado ya está transcribiéndose; se pasa directo a verlo.
  const openTranscription = (recording: Recording) =>
    navigate({ to: "/transcription", search: { recording: recording.id } });

  return (
    <ModulePage stepId="recordings" connected>
      <Card size="3">
        <Flex direction="column" gap="5">
          <PatientField value={patientReference} onChange={setPatientReference} />
          <Recorder patientReference={patientReference.trim()} onSaved={openTranscription} />
        </Flex>
      </Card>

      <RecordingsList />
    </ModulePage>
  );
}

/** El paciente se fija antes de grabar para no mezclar dictados entre pacientes. */
function PatientField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <Flex direction="column" gap="1">
      <Text as="label" htmlFor="patient-reference" size="2" weight="medium">
        Paciente / cama
      </Text>
      <TextField.Root
        id="patient-reference"
        size="3"
        placeholder="Ej.: Cama 4 · UCI"
        value={value}
        maxLength={120}
        onChange={(event) => onChange(event.target.value)}
      />
      <Text size="1" color="gray">
        Confirma el paciente antes de grabar. Usa datos ficticios durante la demo.
      </Text>
    </Flex>
  );
}

interface RecorderProps {
  patientReference: string;
  onSaved: (recording: Recording) => void;
}

function Recorder({ patientReference, onSaved }: RecorderProps) {
  const recorder = useAudioRecorder();
  const upload = useUploadRecording();
  const [note, setNote] = useState("");
  const { status, audio } = recorder;
  const canStart = patientReference.length > 0;
  const isLive = status === "recording" || status === "paused";

  const save = () => {
    if (!audio) return;
    upload.mutate(
      {
        audio: audio.blob,
        source: "in_app",
        recordedAt: audio.startedAt,
        durationSeconds: audio.durationSeconds,
        patientReference,
        note,
      },
      {
        onSuccess: (recording) => {
          onSaved(recording);
          setNote("");
          recorder.reset();
          upload.reset();
        },
      },
    );
  };

  const discard = () => {
    setNote("");
    upload.reset();
    recorder.reset();
  };

  return (
    <Flex direction="column" align="center" gap="4">
      <Flex align="center" justify="center" style={{ width: 96, height: 96 }}>
        {status === "stopped" ? (
          <span className="step-icon" style={{ width: 80, height: 80, borderRadius: 999 }}>
            <StepIcon id="recordings" size={28} />
          </span>
        ) : (
          <span className={status === "recording" ? "record-ring" : undefined} style={{ borderRadius: 999 }}>
            <Button
              size="4"
              color="red"
              variant={isLive ? "soft" : "solid"}
              radius="full"
              disabled={(!canStart && !isLive) || status === "requesting"}
              onClick={isLive ? recorder.stop : recorder.start}
              aria-label={isLive ? "Detener grabación" : "Comenzar grabación"}
              style={{ width: 80, height: 80 }}
            >
              {status === "requesting" ? <Spinner size="3" /> : isLive ? <StopGlyph /> : <StepIcon id="recordings" size={28} />}
            </Button>
          </span>
        )}
      </Flex>

      <Flex direction="column" align="center" gap="1">
        <Text
          size="7"
          weight="medium"
          color={status === "recording" ? "red" : undefined}
          style={{ fontVariantNumeric: "tabular-nums", letterSpacing: "-0.02em" }}
        >
          {formatDuration(status === "stopped" ? audio?.durationSeconds : recorder.elapsedSeconds)}
        </Text>
        <Text size="2" color="gray" align="center">
          {statusHint(status, canStart)}
        </Text>
      </Flex>

      {status !== "stopped" && (
        <Box className="waveform" data-live={status === "recording" || undefined} aria-hidden="true">
          {recorder.levels.map((level, index) => (
            <span key={index} style={{ height: `${Math.max(8, level * 100)}%` }} />
          ))}
        </Box>
      )}

      {isLive && (
        <Flex gap="3">
          {status === "recording" ? (
            <Button variant="soft" color="gray" radius="full" onClick={recorder.pause}>
              Pausar
            </Button>
          ) : (
            <Button variant="soft" radius="full" onClick={recorder.resume}>
              Reanudar
            </Button>
          )}
          <Button variant="soft" color="gray" radius="full" onClick={recorder.reset}>
            Descartar
          </Button>
        </Flex>
      )}

      {status === "stopped" && audio && (
        <Flex direction="column" gap="3" style={{ width: "100%", maxWidth: 520 }}>
          <audio controls src={audio.url} style={{ width: "100%" }} />
          <TextArea
            placeholder="Nota opcional (p. ej.: evaluación de ingreso, control de las 08:00)"
            value={note}
            maxLength={255}
            onChange={(event) => setNote(event.target.value)}
          />
          {upload.isError && (
            <Callout.Root color="red" size="1">
              <Callout.Text>No se pudo guardar: {upload.error.message}. El audio sigue disponible aquí.</Callout.Text>
            </Callout.Root>
          )}
          <Flex gap="3" justify="end" wrap="wrap">
            <Button variant="soft" color="gray" onClick={discard} disabled={upload.isPending}>
              Descartar
            </Button>
            <Button onClick={save} loading={upload.isPending} disabled={!canStart}>
              Guardar y transcribir
            </Button>
          </Flex>
        </Flex>
      )}

      {recorder.error && (
        <Callout.Root color="red" size="1">
          <Callout.Text>{recorder.error}</Callout.Text>
        </Callout.Root>
      )}

      {!isLive && status !== "stopped" && (
        <FileUpload patientReference={patientReference} onSaved={onSaved} prominent={!isRecordingSupported()} />
      )}
    </Flex>
  );
}

function statusHint(status: ReturnType<typeof useAudioRecorder>["status"], canStart: boolean): string {
  switch (status) {
    case "requesting":
      return "Esperando permiso para usar el micrófono…";
    case "recording":
      return "Grabando. Menciona hora, signos vitales, medicamentos y reacciones.";
    case "paused":
      return "En pausa.";
    case "stopped":
      return "Escucha el dictado y guárdalo para transcribirlo.";
    default:
      return canStart ? "Pulsa para comenzar a dictar." : "Indica el paciente para habilitar la grabación.";
  }
}

function StopGlyph() {
  return <span aria-hidden="true" style={{ width: 22, height: 22, borderRadius: 4, background: "currentColor" }} />;
}

/** Alternativa: subir un audio grabado con otra aplicación. */
function FileUpload({ patientReference, onSaved, prominent }: RecorderProps & { prominent: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const upload = useUploadRecording();

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    upload.mutate(
      {
        audio: file,
        source: "upload",
        filename: file.name,
        recordedAt: new Date(file.lastModified),
        durationSeconds: await readAudioDuration(file),
        patientReference,
      },
      { onSuccess: onSaved },
    );
  };

  return (
    <Flex direction="column" align="center" gap="2">
      <input ref={input} type="file" accept="audio/*" hidden onChange={onFile} />
      <Button
        variant={prominent ? "solid" : "ghost"}
        color={prominent ? undefined : "gray"}
        size="2"
        disabled={!patientReference}
        loading={upload.isPending}
        onClick={() => input.current?.click()}
      >
        ¿Ya tienes el audio? Subir archivo
      </Button>
      {upload.isError && (
        <Callout.Root color="red" size="1">
          <Callout.Text>No se pudo subir: {upload.error.message}</Callout.Text>
        </Callout.Root>
      )}
    </Flex>
  );
}

/** Duración leyendo los metadatos del archivo; `null` si el navegador no puede. */
function readAudioDuration(file: Blob): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const element = new Audio();
    const done = (value: number | null) => {
      URL.revokeObjectURL(url);
      resolve(value !== null && Number.isFinite(value) ? value : null);
    };
    element.preload = "metadata";
    element.onloadedmetadata = () => done(element.duration);
    element.onerror = () => done(null);
    element.src = url;
  });
}

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });

function RecordingsList() {
  const { data: recordings = [], isPending, isError, error } = useRecordings();

  return (
    <Flex direction="column" gap="3">
      <Heading size="4">Mis dictados</Heading>
      {isError ? (
        <Callout.Root color="red">
          <Callout.Text>No se pudieron cargar los dictados: {error.message}</Callout.Text>
        </Callout.Root>
      ) : !isPending && recordings.length === 0 ? (
        <EmptyState title="Aún no hay dictados" description="Los audios que grabes o subas aparecerán aquí." />
      ) : (
        <Table.Root variant="surface">
          <Table.Header>
            <Table.Row>
              <Table.ColumnHeaderCell>Paciente</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell>Fecha</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell>Duración</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell>Origen</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell>Audio</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell />
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {recordings.map((recording) => (
              <Table.Row key={recording.id} align="center">
                <Table.RowHeaderCell>
                  <Flex direction="column">
                    <Text weight="medium">{recording.patientReference || "—"}</Text>
                    {recording.note && (
                      <Text size="1" color="gray">
                        {recording.note}
                      </Text>
                    )}
                  </Flex>
                </Table.RowHeaderCell>
                <Table.Cell>{DATE_FORMAT.format(new Date(recording.recordedAt))}</Table.Cell>
                <Table.Cell>
                  <Flex direction="column">
                    <Text>{formatDuration(recording.durationSeconds)}</Text>
                    <Text size="1" color="gray">
                      {formatBytes(recording.sizeBytes)}
                    </Text>
                  </Flex>
                </Table.Cell>
                <Table.Cell>
                  <Badge color={recording.source === "in_app" ? "red" : "gray"} variant="soft">
                    {recording.source === "in_app" ? "Grabado en app" : "Archivo subido"}
                  </Badge>
                </Table.Cell>
                <Table.Cell>
                  <audio controls preload="none" src={recording.audioUrl} style={{ height: 32, maxWidth: 220 }} />
                </Table.Cell>
                <Table.Cell>
                  <DeleteRecordingButton recording={recording} />
                </Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table.Root>
      )}
    </Flex>
  );
}

function DeleteRecordingButton({ recording }: { recording: Recording }) {
  const remove = useDeleteRecording();
  return (
    <AlertDialog.Root>
      <AlertDialog.Trigger>
        <IconButton variant="ghost" color="gray" aria-label="Eliminar dictado" loading={remove.isPending}>
          <TrashGlyph />
        </IconButton>
      </AlertDialog.Trigger>
      <AlertDialog.Content maxWidth="420px">
        <AlertDialog.Title>¿Eliminar este dictado?</AlertDialog.Title>
        <AlertDialog.Description size="2">
          Se borrará el audio de {recording.patientReference || "este paciente"}. No se puede deshacer.
        </AlertDialog.Description>
        <Flex gap="3" mt="4" justify="end">
          <AlertDialog.Cancel>
            <Button variant="soft" color="gray">
              Cancelar
            </Button>
          </AlertDialog.Cancel>
          <AlertDialog.Action>
            <Button color="red" onClick={() => remove.mutate(recording.id)}>
              Eliminar
            </Button>
          </AlertDialog.Action>
        </Flex>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
}

function TrashGlyph() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}
