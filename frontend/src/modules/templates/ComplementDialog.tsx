import { useRef, useState, type ChangeEvent } from "react";
import { Button, Callout, Dialog, Flex, Text, TextArea } from "@radix-ui/themes";
import { formatDuration } from "../recordings/recorderFormat";
import { isRecordingSupported, useAudioRecorder } from "../recordings/useAudioRecorder";
import { useComplementSection } from "./api";

interface ComplementDialogProps {
  extractionId: string;
  section: string;
  label: string;
  disabled?: boolean;
  /** Texto del botón (por defecto «Agregar información»; p. ej. «Corregir» al revisar). */
  triggerLabel?: string;
}

/** Permite completar una sección escribiendo, grabando un audio o subiendo un archivo. */
export function ComplementDialog({ extractionId, section, label, disabled, triggerLabel = "Agregar información" }: ComplementDialogProps) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger>
        <Button size="1" variant="soft" disabled={disabled}>
          {triggerLabel}
        </Button>
      </Dialog.Trigger>
      <Dialog.Content maxWidth="480px">
        <Dialog.Title>{label}</Dialog.Title>
        <Dialog.Description size="2" color="gray">
          Escribe o dicta la información que falta. Se incorporará a esta sección del registro.
        </Dialog.Description>
        <ComplementForm extractionId={extractionId} section={section} onDone={() => setOpen(false)} />
      </Dialog.Content>
    </Dialog.Root>
  );
}

interface ComplementFormProps {
  extractionId: string;
  section: string;
  onDone: () => void;
}

function ComplementForm({ extractionId, section, onDone }: ComplementFormProps) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const recorder = useAudioRecorder();
  const complement = useComplementSection();

  const recorded = recorder.status === "stopped" ? recorder.audio : null;
  const audio: Blob | null = recorded?.blob ?? file;
  const canSend = text.trim().length > 0 || audio !== null;

  const send = () =>
    complement.mutate(
      {
        extractionId,
        section,
        text: text.trim() || undefined,
        audio: audio ?? undefined,
        audioFilename: file?.name,
      },
      {
        onSuccess: () => {
          recorder.reset();
          onDone();
        },
      },
    );

  return (
    <Flex direction="column" gap="3" mt="3">
      <TextArea
        placeholder="Escribe aquí la información que falta…"
        rows={4}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />

      <AudioPicker recorder={recorder} file={file} onFile={setFile} />

      {complement.isError && (
        <Callout.Root color="red" size="1">
          <Callout.Text>No se pudo enviar: {complement.error.message}</Callout.Text>
        </Callout.Root>
      )}

      <Flex gap="3" justify="end">
        <Dialog.Close>
          <Button variant="soft" color="gray" disabled={complement.isPending}>
            Cancelar
          </Button>
        </Dialog.Close>
        <Button onClick={send} disabled={!canSend} loading={complement.isPending}>
          Incorporar al registro
        </Button>
      </Flex>
    </Flex>
  );
}

interface AudioPickerProps {
  recorder: ReturnType<typeof useAudioRecorder>;
  file: File | null;
  onFile: (file: File | null) => void;
}

function AudioPicker({ recorder, file, onFile }: AudioPickerProps) {
  const input = useRef<HTMLInputElement>(null);
  const { status, audio } = recorder;

  const pickFile = (event: ChangeEvent<HTMLInputElement>) => {
    onFile(event.target.files?.[0] ?? null);
    event.target.value = "";
  };

  if (status === "stopped" && audio) {
    return (
      <Flex direction="column" gap="2">
        <audio controls src={audio.url} style={{ width: "100%", height: 36 }} />
        <Flex>
          <Button size="1" variant="ghost" color="gray" onClick={recorder.reset}>
            Descartar audio
          </Button>
        </Flex>
      </Flex>
    );
  }

  if (status === "recording" || status === "paused") {
    return (
      <Flex align="center" gap="3">
        <Button color="red" onClick={recorder.stop}>
          Detener grabación
        </Button>
        <Text color="red" style={{ fontVariantNumeric: "tabular-nums" }}>
          {formatDuration(recorder.elapsedSeconds)}
        </Text>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap="2">
      <input ref={input} type="file" accept="audio/*" hidden onChange={pickFile} />
      <Flex align="center" gap="2" wrap="wrap">
        <Button
          variant="soft"
          color="red"
          disabled={!isRecordingSupported() || status === "requesting"}
          onClick={() => {
            onFile(null);
            void recorder.start();
          }}
        >
          Grabar audio
        </Button>
        <Button variant="soft" color="gray" onClick={() => input.current?.click()}>
          Subir archivo de audio
        </Button>
        {file && (
          <Flex align="center" gap="2">
            <Text size="2">{file.name}</Text>
            <Button size="1" variant="ghost" color="gray" onClick={() => onFile(null)}>
              Quitar
            </Button>
          </Flex>
        )}
      </Flex>
      {recorder.error && (
        <Text size="1" color="red">
          {recorder.error}
        </Text>
      )}
    </Flex>
  );
}
