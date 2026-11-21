import { useRef, useState, type ChangeEvent } from "react";
import {
  Box,
  Button,
  Callout,
  Card,
  Flex,
  Select,
  Spinner,
  Text,
  TextArea,
} from "@radix-ui/themes";
import { useNavigate } from "@tanstack/react-router";
import { ModulePage } from "../../components/ModulePage";
import { StepIcon } from "../../components/icons";
import { useUploadRecording, type Recording } from "./api";
import { usePatients } from "../patients/api";
import { PipelineView } from "../pipeline/PipelineView";
import { formatDuration } from "./recorderFormat";
import { isRecordingSupported, useAudioRecorder } from "./useAudioRecorder";

interface RecordingsPageProps {
  /** Dictado cuyo proceso (transcripción → informe) se está mostrando. */
  recordingId?: string;
}

export function RecordingsPage({ recordingId }: RecordingsPageProps) {
  const [patientId, setPatientId] = useState<number | undefined>();
  const navigate = useNavigate();
  // El dictado guardado ya se está procesando solo: se muestra el avance aquí mismo.
  const showProcess = (recording: Recording) => navigate({ to: "/recordings", search: { recording: recording.id } });

  return (
    <ModulePage stepId="recordings" connected>
      <Card size="3">
        <Flex direction="column" gap="5">
          <PatientPicker value={patientId} onChange={setPatientId} />
          <Recorder patientId={patientId} onSaved={showProcess} />
        </Flex>
      </Card>

      {recordingId && (
        <PipelineView
          key={recordingId}
          recordingId={recordingId}
          onMissing={() => navigate({ to: "/recordings", search: {}, replace: true })}
        />
      )}
    </ModulePage>
  );
}

/** El paciente se elige entre los asignados antes de grabar: identifica de quién es el dictado y el informe. */
function PatientPicker({ value, onChange }: { value: number | undefined; onChange: (id: number) => void }) {
  const { data: patients = [], isPending } = usePatients();
  const selected = patients.find((patient) => patient.id === value);

  return (
    <Flex direction="column" gap="1">
      <Text as="label" size="2" weight="medium">
        Paciente
      </Text>
      <Flex gap="3" wrap="wrap" align="center">
        <Select.Root value={selected ? String(selected.id) : undefined} onValueChange={(id) => onChange(Number(id))}>
          <Select.Trigger
            placeholder={isPending ? "Cargando pacientes…" : patients.length === 0 ? "No tienes pacientes asignados" : "Elige un paciente asignado"}
            style={{ minWidth: 300 }}
          />
          <Select.Content>
            {patients.map((patient) => (
              <Select.Item key={patient.id} value={String(patient.id)}>
                {patient.reference}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </Flex>
      <Text size="1" color="gray">
        Solo aparecen los pacientes que tienes asignados (vienen de otro sistema o te los traspasa otro usuario). El
        audio se nombra solo con tu cuenta, el profesional y la hora.
      </Text>
    </Flex>
  );
}

interface RecorderProps {
  patientId: number | undefined;
  onSaved: (recording: Recording) => void;
}

function Recorder({ patientId, onSaved }: RecorderProps) {
  const recorder = useAudioRecorder();
  const upload = useUploadRecording();
  const [note, setNote] = useState("");
  const { status, audio } = recorder;
  const canStart = patientId !== undefined;
  const isLive = status === "recording" || status === "paused";

  const save = () => {
    if (!audio) return;
    upload.mutate(
      {
        audio: audio.blob,
        source: "in_app",
        recordedAt: audio.startedAt,
        durationSeconds: audio.durationSeconds,
        patientId,
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
        <FileUpload
          patientId={patientId}
          onSaved={onSaved}
          prominent={!isRecordingSupported()}
        />
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
      return canStart ? "Pulsa para comenzar a dictar." : "Elige un paciente asignado para habilitar la grabación.";
  }
}

function StopGlyph() {
  return <span aria-hidden="true" style={{ width: 22, height: 22, borderRadius: 4, background: "currentColor" }} />;
}

/** Alternativa: subir un audio grabado con otra aplicación. */
function FileUpload({ patientId, onSaved, prominent }: RecorderProps & { prominent: boolean }) {
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
        patientId,
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
        disabled={patientId === undefined}
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
