import { useMemo, useState } from "react";
import {
  AlertDialog,
  Button,
  Callout,
  Card,
  Checkbox,
  Flex,
  Grid,
  Heading,
  Select,
  Spinner,
  Table,
  Text,
  TextField,
} from "@radix-ui/themes";
import { EmptyState } from "../../components/EmptyState";
import { ModulePage } from "../../components/ModulePage";
import { useClosePending, useEpisodeRecords, useHandoffs, useSendHandoff, useTeam } from "../episode/api";
import { SourceLink } from "../episode/components";
import { formatClinicalTime } from "../episode/format";
import { buildHandoffSnapshots, handoffReferenceAt } from "../episode/handoff";
import type { EpisodePatient, EpisodeRecord, Handoff, HandoffSnapshot, OpenConflict, PendingTask } from "../episode/model";
import { PRIORITY_THRESHOLDS, rankPatients } from "../episode/priority";
import type { Team } from "../episode/gateway";
import { authorLine, professionalById } from "../episode/record";
import { PatientPriorityList } from "./PatientPriorityList";
import { PatientStatusCard } from "./PatientStatusCard";
import { SnapshotView } from "./SnapshotView";

type People = Pick<EpisodeRecord, "professionals">;

export function HandoffPage() {
  const records = useEpisodeRecords();
  const team = useTeam();

  return (
    <ModulePage stepId="handoff" connected>
      {records.isPending || team.isPending ? (
        <Flex justify="center" py="6"><Spinner size="3" /></Flex>
      ) : !records.data || !team.data ? (
        <EmptyState
          title="No se pudo cargar el traspaso"
          description={(records.error ?? team.error)?.message ?? "Inténtalo de nuevo en unos segundos."}
        />
      ) : (
        <SendHandoff records={records.data} team={team.data} actorId={team.data.meId} />
      )}
    </ModulePage>
  );
}

interface SendHandoffProps {
  records: EpisodeRecord[];
  team: Team;
  actorId: string;
}

function SendHandoff({ records, team, actorId }: SendHandoffProps) {
  const recipients = team.professionals.filter(({ id }) => team.recipientIds.includes(id));
  const [toId, setToId] = useState("");
  const [note, setNote] = useState("");
  const send = useSendHandoff();
  const handoffs = useHandoffs();
  const snapshots = useMemo(() => buildHandoffSnapshots(records, actorId), [records, actorId]);
  const recipient = professionalById(team, toId);
  // Los pacientes se reparten: cada envío lleva solo los marcados, y los ya enviados se desmarcan.
  const [excluded, setExcluded] = useState<ReadonlySet<string>>(new Set());
  const selected = snapshots.filter(({ episodeId }) => !excluded.has(episodeId));
  const sentTo = recipientsByPatient(handoffs.data ?? [], actorId, team);
  const toggle = (episodeId: string, checked: boolean) =>
    setExcluded((current) => {
      const next = new Set(current);
      if (checked) next.delete(episodeId);
      else next.add(episodeId);
      return next;
    });

  if (snapshots.length === 0) {
    return (
      <EmptyState
        title="Sin pacientes para traspasar"
        description="Aquí aparecen los pacientes que atendiste (con informes guardados) para entregarlos a otra persona."
      />
    );
  }

  return (
    <Flex direction="column" gap="4">
      <Card>
        <Flex direction="column" gap="3">
          <Flex gap="3" align="end" wrap="wrap">
            <Flex direction="column" gap="1" style={{ flex: "1 1 220px" }}>
              <Text size="1" color="gray">Entregar a</Text>
              <Select.Root value={toId} onValueChange={setToId}>
                <Select.Trigger placeholder="Persona destinataria" aria-label="Destinatario" style={{ width: "100%" }} />
                <Select.Content>
                  {recipients.map((professional) => (
                    <Select.Item key={professional.id} value={professional.id}>
                      {professional.name} · {professional.role}
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </Flex>
            <Flex direction="column" gap="1" style={{ flex: "3 1 280px" }}>
              <Text size="1" color="gray">Nota (opcional)</Text>
              <TextField.Root
                aria-label="Nota de la entrega"
                placeholder="Nota para la persona que recibe el turno"
                value={note}
                maxLength={1000}
                onChange={(event) => setNote(event.target.value)}
              />
            </Flex>
            <AlertDialog.Root>
              <AlertDialog.Trigger>
                <Button disabled={!recipient || selected.length === 0} loading={send.isPending}>
                  Enviar traspaso
                </Button>
              </AlertDialog.Trigger>
              <AlertDialog.Content maxWidth="440px">
                <AlertDialog.Title>Confirmar traspaso</AlertDialog.Title>
                <AlertDialog.Description size="2">
                  Se enviará a {recipient?.name} una sola entrega con {patientCount(selected.length)}. Quien la reciba
                  pasará a ver a esos pacientes. Los demás los puedes entregar a otra persona.
                </AlertDialog.Description>
                <Flex gap="3" mt="4" justify="end">
                  <AlertDialog.Cancel><Button variant="soft" color="gray">Cancelar</Button></AlertDialog.Cancel>
                  <AlertDialog.Action>
                    <Button
                      onClick={() => {
                        const episodeIds = selected.map(({ episodeId }) => episodeId);
                        send.mutate(
                          { fromId: actorId, toId, note, episodeIds },
                          {
                            onSuccess: () => {
                              setNote("");
                              setExcluded((current) => new Set([...current, ...episodeIds]));
                            },
                          },
                        );
                      }}
                    >
                      Confirmar envío
                    </Button>
                  </AlertDialog.Action>
                </Flex>
              </AlertDialog.Content>
            </AlertDialog.Root>
          </Flex>
          <Flex direction="column" gap="2">
            <Text size="2" weight="medium">
              Pacientes a entregar ({selected.length} de {snapshots.length}) · atendidos por {authorLine(team, actorId)}
            </Text>
            <Table.Root variant="surface" size="1" aria-label="Pacientes a entregar">
              <Table.Header>
                <Table.Row>
                  <Table.ColumnHeaderCell width="40px">
                    <Checkbox
                      checked={selected.length === snapshots.length ? true : selected.length === 0 ? false : "indeterminate"}
                      onCheckedChange={(checked) =>
                        setExcluded(checked === true ? new Set() : new Set(snapshots.map(({ episodeId }) => episodeId)))
                      }
                      aria-label="Marcar o desmarcar todos los pacientes"
                    />
                  </Table.ColumnHeaderCell>
                  <Table.ColumnHeaderCell>Nombre</Table.ColumnHeaderCell>
                  <Table.ColumnHeaderCell>RUT</Table.ColumnHeaderCell>
                  <Table.ColumnHeaderCell>Box</Table.ColumnHeaderCell>
                </Table.Row>
              </Table.Header>
              <Table.Body>
                {snapshots.map((snapshot) => {
                  const patient = patientColumns(records, snapshot);
                  return (
                    <Table.Row key={snapshot.episodeId} align="center">
                      <Table.Cell>
                        <Checkbox
                          checked={!excluded.has(snapshot.episodeId)}
                          onCheckedChange={(checked) => toggle(snapshot.episodeId, checked === true)}
                          aria-label={`Entregar a ${snapshot.episodeLabel}`}
                        />
                      </Table.Cell>
                      <Table.Cell>
                        <Flex direction="column">
                          <Text size="2">{patient.name}</Text>
                          {sentTo.get(snapshot.episodeId) && (
                            <Text size="1" color="gray">Ya entregado a {sentTo.get(snapshot.episodeId)}</Text>
                          )}
                        </Flex>
                      </Table.Cell>
                      <Table.Cell>{patient.identifier || "—"}</Table.Cell>
                      <Table.Cell>{patient.bed || "—"}</Table.Cell>
                    </Table.Row>
                  );
                })}
              </Table.Body>
            </Table.Root>
          </Flex>
          {send.error && (
            <Callout.Root color="red"><Callout.Text>{send.error.message}</Callout.Text></Callout.Root>
          )}
          {send.data && !send.isPending && (
            <Callout.Root color="green">
              <Callout.Text>
                Traspaso de {patientCount(send.data.snapshots.length)} enviado a{" "}
                {professionalById(team, send.data.toId)?.name}.
              </Callout.Text>
            </Callout.Root>
          )}
        </Flex>
      </Card>
      {selected.length > 0 && (
        <PatientSnapshots records={records} team={team} snapshots={selected} actorId={actorId} />
      )}
    </Flex>
  );
}

/** A quién ya le entregaste cada paciente («Ana Morales, Tomás Ibarra»), según tus traspasos enviados. */
function recipientsByPatient(handoffs: Handoff[], actorId: string, team: People): Map<string, string> {
  const names = new Map<string, Set<string>>();
  for (const handoff of handoffs.filter(({ fromId }) => fromId === actorId)) {
    const name = professionalById(team, handoff.toId)?.name;
    if (!name) continue;
    for (const { episodeId } of handoff.snapshots) {
      names.set(episodeId, (names.get(episodeId) ?? new Set()).add(name));
    }
  }
  return new Map([...names].map(([episodeId, people]) => [episodeId, [...people].join(", ")]));
}

/** Nombre, RUT y box del paciente; si el registro no los trae por separado, el nombre es la etiqueta completa. */
function patientColumns(records: EpisodeRecord[], snapshot: HandoffSnapshot): EpisodePatient {
  const patient = records.find(({ episode }) => episode.id === snapshot.episodeId)?.episode.patient;
  return patient ?? { name: snapshot.episodeLabel, identifier: "", bed: "" };
}

function PatientSnapshots({ records, team, snapshots, actorId }: {
  records: EpisodeRecord[];
  team: People;
  snapshots: HandoffSnapshot[];
  actorId?: string;
}) {
  const [episodeId, setEpisodeId] = useState<string>();
  const referenceAt = handoffReferenceAt(snapshots);
  const patients = referenceAt ? rankPatients(snapshots, referenceAt) : [];
  const snapshot = patients.find((item) => item.snapshot.episodeId === episodeId)?.snapshot ?? patients[0]?.snapshot;
  if (!snapshot || !referenceAt) return null;

  const record = records.find(({ episode }) => episode.id === snapshot.episodeId);

  return (
    <Grid columns={{ initial: "1", md: "minmax(240px, 1fr) 2fr" }} gap="4" align="start">
      <PatientPriorityList
        patients={patients}
        referenceAt={referenceAt}
        selectedId={snapshot.episodeId}
        onSelect={setEpisodeId}
      />
      <Card size="3">
        <Flex direction="column" gap="4">
          <PatientStatusCard team={team} snapshot={snapshot} referenceAt={referenceAt} />
          <ConflictNotes episodeId={snapshot.episodeId} conflicts={snapshot.openConflicts ?? []} />
          <PatientTodo
            key={snapshot.episodeId}
            team={team}
            snapshot={snapshot}
            record={record}
            referenceAt={referenceAt}
            actorId={actorId}
          />
          <SnapshotView record={team} snapshot={snapshot} />
        </Flex>
      </Card>
    </Grid>
  );
}

/** Conflictos como notas sobrias: franja ámbar y texto normal, sin bloque de color. */
function ConflictNotes({ episodeId, conflicts }: { episodeId: string; conflicts: OpenConflict[] }) {
  if (conflicts.length === 0) return null;

  return (
    <Flex direction="column" gap="2" role="region" aria-label="Conflictos por revisar">
      {conflicts.map((conflict) => (
        <Flex key={conflict.id} direction="column" gap="1" pl="3" style={{ borderLeft: "3px solid var(--amber-9)" }}>
          <Text size="1" color="amber" weight="medium">Conflicto por revisar</Text>
          <Text size="2">{conflict.description}</Text>
          <Text size="1" color="gray">
            {conflict.sourceEncounterIds.map((id, index) => (
              <span key={id}>
                {index > 0 && " · "}
                <SourceLink episodeId={episodeId} encounterId={id}>
                  {conflict.sourceEncounterIds.length === 1 ? "ver atención de origen" : `ver atención ${index + 1}`}
                </SourceLink>
              </span>
            ))}
          </Text>
        </Flex>
      ))}
    </Flex>
  );
}

/**
 * Pendientes abiertos al enviar, del más urgente al menos urgente. Solo lo
 * vencido o por vencer lleva color; el estado vivo se superpone (cerrado
 * después del envío) y quien recibe puede cerrarlos aquí mismo.
 */
function PatientTodo({ team, snapshot, record, referenceAt, actorId }: {
  team: People;
  snapshot: HandoffSnapshot;
  record: EpisodeRecord | undefined;
  referenceAt: string;
  actorId?: string;
}) {
  const close = useClosePending();
  const pendings = snapshot.pendings
    .filter(({ status }) => status === "open")
    .sort((a, b) => dueTime(a) - dueTime(b));

  return (
    <Flex direction="column" gap="2" role="region" aria-label="Por hacer">
      <Heading size="3">Por hacer</Heading>
      {close.error && (
        <Callout.Root color="red"><Callout.Text>{close.error.message}</Callout.Text></Callout.Root>
      )}
      {pendings.length === 0 && <Text size="2" color="gray">Sin pendientes abiertos al corte.</Text>}
      {pendings.map((pending) => {
        const live = record?.pendings.find(({ id }) => id === pending.id);
        const closedNow = live?.status === "done";
        return (
          <Flex key={pending.id} align="center" justify="between" gap="3">
            <Flex direction="column" gap="1">
              <Text size="2" color={closedNow ? "gray" : undefined} style={closedNow ? { textDecoration: "line-through" } : undefined}>
                {pending.title}
              </Text>
              <Text size="1" color="gray">
                {closedNow ? "Cerrado después del envío" : <DueLabel dueAt={pending.dueAt} referenceAt={referenceAt} />}
                {" · "}{authorLine(team, pending.ownerId)} ·{" "}
                <SourceLink episodeId={snapshot.episodeId} encounterId={pending.sourceEncounterId}>origen</SourceLink>
              </Text>
            </Flex>
            {actorId && record && live?.status === "open" && (
              <Button
                size="1"
                variant="ghost"
                color="gray"
                aria-label={`Cerrar pendiente: ${pending.title}`}
                disabled={close.isPending}
                loading={close.isPending && close.variables?.pendingId === pending.id}
                onClick={() => close.mutate({ episodeId: record.episode.id, pendingId: pending.id })}
              >
                Cerrar
              </Button>
            )}
          </Flex>
        );
      })}
    </Flex>
  );
}

function dueTime({ dueAt }: PendingTask): number {
  return dueAt ? Date.parse(dueAt) : Number.POSITIVE_INFINITY;
}

function DueLabel({ dueAt, referenceAt }: { dueAt: string | null; referenceAt: string }) {
  if (!dueAt) return <>Sin plazo</>;
  const hoursLeft = (Date.parse(dueAt) - Date.parse(referenceAt)) / 3_600_000;
  const time = formatClinicalTime(dueAt);
  if (hoursLeft <= 0) return <Text color="red" weight="medium">Vencido · plazo {time}</Text>;
  if (hoursLeft <= PRIORITY_THRESHOLDS.upcomingDueHours) return <Text color="amber" weight="medium">Vence {time}</Text>;
  return <>Plazo {time}</>;
}

function patientCount(count: number): string {
  return `${count} ${count === 1 ? "paciente" : "pacientes"}`;
}
