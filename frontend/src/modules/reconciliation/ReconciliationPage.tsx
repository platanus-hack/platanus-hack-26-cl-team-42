import { useState } from "react";
import { Badge, Button, Callout, Card, Flex, Grid, Heading, Text, TextArea } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
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

  return (
    <ModulePage stepId="reconciliation" connected>
      <Text size="2" color="gray">
        Cuando un informe guardado contradice lo ya reportado por otro profesional (o por ti), se compara con la versión
        oficial del paciente y se abre una reconciliación. Quedan registradas las notas y razones de cada uno.
      </Text>

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
        <Grid columns={{ initial: "1", md: "280px 1fr" }} gap="4">
          <Flex direction="column" gap="2">
            <Heading size="4">Reconciliaciones</Heading>
            {reconciliations.map((item) => (
              <Button
                key={item.id}
                variant={item.id === selected?.id ? "solid" : "soft"}
                onClick={() => setSelectedId(item.id)}
                style={{ justifyContent: "space-between", height: "auto", padding: "8px 12px" }}
              >
                <Flex direction="column" align="start" style={{ textAlign: "left" }}>
                  <span>{item.patientName}</span>
                  <Text size="1">
                    {item.reportTitle} · {resolvedCount(item)} de {item.conflicts.length} resueltos
                  </Text>
                </Flex>
                <Badge color={item.status === "open" ? "orange" : "green"} variant="surface" radius="full">
                  {item.status === "open" ? "Abierta" : "Resuelta"}
                </Badge>
              </Button>
            ))}
          </Flex>
          {selected && <ReconciliationDetail reconciliation={selected} />}
        </Grid>
      )}
    </ModulePage>
  );
}

function resolvedCount(reconciliation: Reconciliation): number {
  return reconciliation.conflicts.filter((conflict) => conflict.status === "resolved").length;
}

function ReconciliationDetail({ reconciliation }: { reconciliation: Reconciliation }) {
  const resolved = reconciliation.status === "resolved";
  return (
    <Flex direction="column" gap="3" style={{ minWidth: 0 }}>
      <Card>
        <Flex direction="column" gap="2">
          <Flex align="center" gap="2" wrap="wrap">
            <Heading size="4">{reconciliation.patientName}</Heading>
            <Badge color={resolved ? "green" : "orange"} variant="soft">
              {resolved ? "Resuelta" : "Abierta"}
            </Badge>
          </Flex>
          <Text size="2" color="gray">
            {reconciliation.reportTitle} · comparado con la versión oficial n.º {reconciliation.baseVersion} · abierta el{" "}
            {DATE_FORMAT.format(new Date(reconciliation.created_at))}
          </Text>
          <Text size="2">
            Participan: <strong>{reconciliation.participants.join(" y ")}</strong>
          </Text>
          {!resolved && !reconciliation.conflicts.some((conflict) => conflict.myRole !== null) && (
            <Callout.Root color="gray" size="1">
              <Callout.Text>
                Lo ves en solo lectura porque el paciente está asignado a ti, pero no participas: solo resuelven quienes
                reportaron. Cámbiate a una de esas cuentas para actuar.
              </Callout.Text>
            </Callout.Root>
          )}
          {resolved ? (
            <Callout.Root color="green" size="1">
              <Callout.Text>
                Todos los conflictos están resueltos: este informe quedó incorporado y la versión oficial vigente es la n.º{" "}
                {reconciliation.resultVersion}. La versión n.º {reconciliation.baseVersion} se conserva en el historial.
              </Callout.Text>
            </Callout.Root>
          ) : (
            <Callout.Root color="orange" size="1">
              <Callout.Text>
                Mientras haya conflictos abiertos, la versión oficial no cambia. {resolvedCount(reconciliation)} de{" "}
                {reconciliation.conflicts.length} resueltos.
              </Callout.Text>
            </Callout.Root>
          )}
          <Flex>
            <Link to="/" search={{ patient: String(reconciliation.patientId) }}>
              Ver el resumen y las versiones del paciente
            </Link>
          </Flex>
        </Flex>
      </Card>
      {reconciliation.conflicts.map((conflict) => (
        <ConflictCard key={conflict.id} conflict={conflict} patientId={reconciliation.patientId} reportId={reconciliation.reportId} />
      ))}
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
