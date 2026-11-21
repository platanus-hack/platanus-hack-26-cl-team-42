import { useCallback, useState } from "react";
import { Badge, Button, Callout, Card, Flex, Grid, Heading, Text, TextArea } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { Toast, type ToastMessage } from "../../components/Toast";
import { ConflictCard } from "./ConflictCard";
import { useIncomingConsults, useReconciliations, useReplyConsult, type IncomingConsult, type Reconciliation } from "./api";

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });

export function ReconciliationPage({ reconciliationId }: { reconciliationId?: string }) {
  const { data: reconciliations = [], isPending, isError, error } = useReconciliations();
  const { data: consults = [] } = useIncomingConsults();
  const [selectedId, setSelectedId] = useState<string | undefined>(reconciliationId);
  const open = reconciliations.filter((item) => item.status === "open");
  const selected =
    reconciliations.find((item) => item.id === selectedId) ?? open[0] ?? reconciliations[0];
  const [toast, closeToast] = useVersionToast(selected);

  return (
    <ModulePage stepId="reconciliation" connected>
      <Toast message={toast} onClose={closeToast} />
      <details>
        <summary style={{ cursor: "pointer", width: "fit-content" }}>
          <Text size="2" color="gray">
            ¿Cómo funciona?
          </Text>
        </summary>
        <Text as="p" size="2" color="gray" mt="2">
          Cuando un informe guardado contradice lo ya reportado por otro profesional (o por ti), se compara con la
          versión oficial del paciente y se abre una reconciliación. Mientras haya conflictos abiertos, la versión
          oficial no cambia. Quedan registradas las notas y razones de cada uno.
        </Text>
      </details>

      {consults.length > 0 && <IncomingConsults consults={consults} />}

      {isError ? (
        <Callout.Root color="red">
          <Callout.Text>No se pudieron cargar las reconciliaciones: {error.message}</Callout.Text>
        </Callout.Root>
      ) : !isPending && reconciliations.length === 0 ? (
        consults.length > 0 ? null : (
        <EmptyState
          title="Sin conflictos"
          description="Cuando un informe que guardes choque con lo reportado por otro profesional, aparecerá aquí."
        />
        )
      ) : (
        <Grid columns={{ initial: "1", md: "240px 1fr" }} gap="4" align="start">
          <Flex direction="column" gap="2">
            <Heading size="3">Reconciliaciones</Heading>
            {reconciliations.map((item) => (
              <ReconciliationItem
                key={item.id}
                reconciliation={item}
                selected={item.id === selected?.id}
                onSelect={() => setSelectedId(item.id)}
              />
            ))}
          </Flex>
          {selected && (
            <Flex direction="column" gap="3" style={{ minWidth: 0 }}>
              {selected.conflicts.map((conflict) => (
                <ConflictCard key={conflict.id} conflict={conflict} patientId={selected.patientId} reportId={selected.reportId} />
              ))}
            </Flex>
          )}
        </Grid>
      )}
    </ModulePage>
  );
}

/**
 * Avisa al abrir una reconciliación pendiente que la versión oficial no cambia todavía, y cuando
 * se resuelve el último conflicto, cuál es la nueva versión oficial.
 */
function useVersionToast(selected: Reconciliation | undefined): [ToastMessage | null, () => void] {
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [seen, setSeen] = useState<Pick<Reconciliation, "id" | "status"> | null>(null);
  if (selected && (seen?.id !== selected.id || seen.status !== selected.status)) {
    setSeen({ id: selected.id, status: selected.status });
    const text = versionToastText(selected, seen);
    if (text) setToast({ id: (toast?.id ?? 0) + 1, text });
  }
  const close = useCallback(() => setToast(null), []);
  return [toast, close];
}

function versionToastText(
  reconciliation: Reconciliation,
  seen: Pick<Reconciliation, "id" | "status"> | null,
): string | null {
  if (seen?.id === reconciliation.id) {
    return seen.status === "open" && reconciliation.status === "resolved"
      ? `Conflictos de ${reconciliation.patientName} resueltos: la versión oficial vigente es la n.º ${reconciliation.resultVersion}.`
      : null;
  }
  return reconciliation.status === "open"
    ? `Mientras haya conflictos abiertos, la versión oficial de ${reconciliation.patientName} no cambia.`
    : null;
}

/** Un paciente en la lista; al seleccionarlo se despliega el contexto de su reconciliación. */
function ReconciliationItem({
  reconciliation,
  selected,
  onSelect,
}: {
  reconciliation: Reconciliation;
  selected: boolean;
  onSelect: () => void;
}) {
  const resolved = reconciliation.status === "resolved";
  return (
    <Flex
      direction="column"
      style={{
        borderRadius: "var(--radius-3)",
        background: selected ? "var(--accent-a3)" : "var(--gray-a2)",
        boxShadow: selected ? "inset 0 0 0 1px var(--accent-a7)" : undefined,
      }}
    >
      <button
        type="button"
        aria-expanded={selected}
        onClick={onSelect}
        style={{ all: "unset", cursor: "pointer", padding: "10px 12px", borderRadius: "var(--radius-3)" }}
      >
        <Flex justify="between" align="start" gap="2">
          <Flex direction="column" gap="1" style={{ minWidth: 0 }}>
            <Text size="2" weight="medium">
              {reconciliation.patientName}
            </Text>
            <Text size="1" color="gray">
              {reconciliation.reportTitle} · {resolvedCount(reconciliation)} de {reconciliation.conflicts.length} resueltos
            </Text>
          </Flex>
          <Badge color={resolved ? "green" : "amber"} variant="soft" radius="full">
            {resolved ? "Resuelta" : "Abierta"}
          </Badge>
        </Flex>
      </button>
      {selected && <ReconciliationContext reconciliation={reconciliation} />}
    </Flex>
  );
}

function resolvedCount(reconciliation: Reconciliation): number {
  return reconciliation.conflicts.filter((conflict) => conflict.status === "resolved").length;
}

function ReconciliationContext({ reconciliation }: { reconciliation: Reconciliation }) {
  const resolved = reconciliation.status === "resolved";
  const participatesInOpenConflict = reconciliation.conflicts.some(
    (conflict) => conflict.status === "open" && conflict.myRole !== null,
  );
  return (
    <Flex direction="column" gap="1" px="3" pb="3">
      <Text size="1" color="gray">
        Comparado con la versión oficial n.º {reconciliation.baseVersion}
      </Text>
      <Text size="1" color="gray">
        Abierta el {DATE_FORMAT.format(new Date(reconciliation.created_at))}
      </Text>
      <Text size="1">
        Participan: <strong>{reconciliation.participants.join(" y ")}</strong>
      </Text>
      {resolved && (
        <Text size="1">
          Versión oficial vigente: <strong>n.º {reconciliation.resultVersion}</strong> (la n.º{" "}
          {reconciliation.baseVersion} queda en el historial)
        </Text>
      )}
      {!resolved && !participatesInOpenConflict && (
        <Text size="1" color="gray">
          Puedes consultar estos conflictos porque el paciente está asignado a tu cuenta. Los resuelven los profesionales
          que reportaron los datos y están de turno.
        </Text>
      )}
      <Text size="1" mt="1">
        <Link to="/" search={{ patient: String(reconciliation.patientId) }}>
          Ver el resumen y las versiones
        </Link>
      </Text>
    </Flex>
  );
}

/** Opiniones externas que otro profesional te pidió: el caso llega sin datos del paciente. */
function IncomingConsults({ consults }: { consults: IncomingConsult[] }) {
  return (
    <Flex direction="column" gap="2">
      <Heading size="4">Opiniones que te pidieron</Heading>
      {consults.map((consult) => (
        <ConsultCard key={consult.id} consult={consult} />
      ))}
    </Flex>
  );
}

function ConsultCard({ consult }: { consult: IncomingConsult }) {
  const reply = useReplyConsult();
  const [body, setBody] = useState("");
  return (
    <Card>
      <Flex direction="column" gap="3">
        <Flex align="center" gap="2">
          <Text weight="medium">Consulta clínica anonimizada</Text>
          <Badge color={consult.status === "answered" ? "green" : "amber"} variant="soft">
            {consult.status === "answered" ? "Respondida" : "Pendiente"}
          </Badge>
        </Flex>
        <Text size="2" style={{ whiteSpace: "pre-wrap" }}>
          {consult.brief}
        </Text>
        {consult.status === "answered" ? (
          <Callout.Root color="green" size="1">
            <Callout.Text>Tu opinión: {consult.reply}</Callout.Text>
          </Callout.Root>
        ) : (
          <Flex direction="column" gap="2">
            <TextArea placeholder="Tu opinión clínica…" value={body} onChange={(event) => setBody(event.target.value)} />
            {reply.isError && (
              <Text size="2" color="red">
                {reply.error.message}
              </Text>
            )}
            <Flex>
              <Button
                disabled={!body.trim()}
                loading={reply.isPending}
                onClick={() => reply.mutate({ consultId: consult.id, body: body.trim() })}
              >
                Enviar opinión
              </Button>
            </Flex>
          </Flex>
        )}
      </Flex>
    </Card>
  );
}
