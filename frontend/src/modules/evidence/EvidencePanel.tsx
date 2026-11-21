import { useState } from "react";
import {
  Badge,
  Button,
  Callout,
  Dialog,
  Flex,
  IconButton,
  Select,
  Skeleton,
  Text,
  TextArea,
  TextField,
} from "@radix-ui/themes";
import {
  EVIDENCE_KIND_LABEL,
  useAddEvidence,
  useEvidence,
  type EvidenceItem,
  type EvidenceKind,
  type EvidenceResult,
} from "./api";

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });
const FLAG_MARK: Record<EvidenceResult["flag"], string> = { high: " ↑", low: " ↓", normal: "", "": "" };

/** Evidencia del paciente además de los dictados: se cruza con los informes al validarlos. */
export function EvidencePanel({ patientId }: { patientId: number }) {
  const { data: items, isPending } = useEvidence(patientId);

  return (
    <Flex direction="column" gap="3">
      <Flex justify="between" align="center" gap="3" wrap="wrap">
        <Text size="1" color="gray">
          Al registrar un informe se revisa si contradice estos resultados y se avisa al validarlo.
        </Text>
        <AddEvidenceDialog patientId={patientId} />
      </Flex>
      {isPending ? (
        <Skeleton height="60px" />
      ) : !items ? (
        <Text size="2" color="gray">No se pudieron cargar los exámenes.</Text>
      ) : items.length === 0 ? (
        <Text size="2" color="gray">
          Aún no hay exámenes cargados para este paciente.
        </Text>
      ) : (
        items.map((item) => <EvidenceRow key={item.id} item={item} />)
      )}
    </Flex>
  );
}

function EvidenceRow({ item }: { item: EvidenceItem }) {
  return (
    <Flex id={`evidence-${item.id}`} tabIndex={-1} direction="column" gap="1" p="2" style={{ borderRadius: "var(--radius-3)", background: "var(--gray-a2)" }}>
      <Flex align="center" gap="2" wrap="wrap">
        <Text size="2" weight="medium">
          {item.title}
        </Text>
        <Badge variant="soft" color="gray" size="1">
          {EVIDENCE_KIND_LABEL[item.kind]}
        </Badge>
        <Text size="1" color="gray">
          {DATE_FORMAT.format(new Date(item.takenAt))} · cargado por {item.createdByName}
        </Text>
      </Flex>
      {item.results.length > 0 && (
        <Flex gap="2" wrap="wrap">
          {item.results.map((result) => (
            <Badge key={result.name} color={FLAG_MARK[result.flag] ? "amber" : "gray"} variant="soft">
              {result.name} {result.value} {result.unit}
              {FLAG_MARK[result.flag]}
            </Badge>
          ))}
        </Flex>
      )}
      {item.findings && <Text size="2">{item.findings}</Text>}
    </Flex>
  );
}

interface ResultDraft {
  name: string;
  value: string;
  unit: string;
}

const EMPTY_RESULT: ResultDraft = { name: "", value: "", unit: "" };

function AddEvidenceDialog({ patientId }: { patientId: number }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<EvidenceKind>("lab");
  const [title, setTitle] = useState("");
  const [takenAt, setTakenAt] = useState(() => localNow());
  const [results, setResults] = useState<ResultDraft[]>([{ ...EMPTY_RESULT }]);
  const [findings, setFindings] = useState("");
  const add = useAddEvidence(patientId);

  const update = (index: number, patch: Partial<ResultDraft>) =>
    setResults((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const submit = () =>
    add.mutate(
      {
        kind,
        title: title.trim(),
        takenAt: new Date(takenAt).toISOString(),
        results: results.filter((row) => row.name.trim()),
        findings,
      },
      {
        onSuccess: () => {
          setOpen(false);
          setTitle("");
          setResults([{ ...EMPTY_RESULT }]);
          setFindings("");
          setTakenAt(localNow());
        },
      },
    );

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) add.reset();
      }}
    >
      <Dialog.Trigger>
        <Button size="1" variant="soft">
          Agregar evidencia
        </Button>
      </Dialog.Trigger>
      <Dialog.Content maxWidth="560px">
        <Dialog.Title>Agregar evidencia</Dialog.Title>
        <Dialog.Description size="2" color="gray">
          Resultados de exámenes, imágenes o cultivos. Los informes de este paciente que estén por validar se revisan de
          nuevo con ella.
        </Dialog.Description>
        <Flex direction="column" gap="3" mt="3">
          <Flex gap="3" wrap="wrap">
            <Select.Root value={kind} onValueChange={(value) => setKind(value as EvidenceKind)}>
              <Select.Trigger aria-label="Tipo de evidencia" />
              <Select.Content>
                {(Object.keys(EVIDENCE_KIND_LABEL) as EvidenceKind[]).map((value) => (
                  <Select.Item key={value} value={value}>
                    {EVIDENCE_KIND_LABEL[value]}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
            <TextField.Root
              style={{ flex: 1, minWidth: 200 }}
              placeholder="Examen (p. ej. Gases arteriales)"
              value={title}
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
            />
          </Flex>
          <TextField.Root type="datetime-local" aria-label="Fecha y hora del examen" value={takenAt} onChange={(event) => setTakenAt(event.target.value)} />

          <Flex direction="column" gap="2">
            <Text size="2" weight="medium">
              Resultados
            </Text>
            {results.map((row, index) => (
              <Flex key={index} gap="2">
                <TextField.Root style={{ flex: 2 }} placeholder="Examen (Lactato)" value={row.name} onChange={(event) => update(index, { name: event.target.value })} />
                <TextField.Root style={{ flex: 1 }} placeholder="Valor" value={row.value} onChange={(event) => update(index, { value: event.target.value })} />
                <TextField.Root style={{ flex: 1 }} placeholder="Unidad" value={row.unit} onChange={(event) => update(index, { unit: event.target.value })} />
                <IconButton
                  variant="ghost"
                  color="gray"
                  aria-label="Quitar resultado"
                  disabled={results.length === 1}
                  onClick={() => setResults((current) => current.filter((_, i) => i !== index))}
                >
                  ✕
                </IconButton>
              </Flex>
            ))}
            <Flex>
              <Button size="1" variant="ghost" onClick={() => setResults((current) => [...current, { ...EMPTY_RESULT }])}>
                + Otro resultado
              </Button>
            </Flex>
            <Text size="1" color="gray">
              La unidad y el rango de referencia de los exámenes conocidos se completan solos; los valores fuera de
              rango se marcan.
            </Text>
          </Flex>

          <TextArea placeholder="Informe en texto (imagen, cultivo…), opcional" value={findings} onChange={(event) => setFindings(event.target.value)} />
          {add.isError && (
            <Callout.Root color="red" size="1">
              <Callout.Text>{add.error.message}</Callout.Text>
            </Callout.Root>
          )}
        </Flex>
        <Flex gap="3" justify="end" mt="4">
          <Dialog.Close>
            <Button variant="soft" color="gray">
              Cancelar
            </Button>
          </Dialog.Close>
          <Button disabled={!title.trim()} loading={add.isPending} onClick={submit}>
            Guardar evidencia
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}

/** Ahora, en el formato de un `<input type="datetime-local">` (hora local). */
function localNow(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}
