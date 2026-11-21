import { useMemo, useState } from "react";
import {
  AlertDialog,
  Button,
  Callout,
  Card,
  Flex,
  Grid,
  Heading,
  Select,
  Spinner,
  Tabs,
  Text,
  TextField,
} from "@radix-ui/themes";
import { useNavigate } from "@tanstack/react-router";
import { EmptyState } from "../../components/EmptyState";
import { ModulePage } from "../../components/ModulePage";
import type { HandoffSearch, HandoffTab } from "../../routes/_authenticated/handoff";
import { useClosePending, useEpisodeRecords, useHandoffs, useResetDemo, useSendHandoff } from "../episode/api";
import { SourceLink } from "../episode/components";
import { formatClinicalTime } from "../episode/format";
import { buildHandoffSnapshots, handoffReferenceAt } from "../episode/handoff";
import type { EpisodeRecord, Handoff, HandoffSnapshot, OpenConflict, PendingTask } from "../episode/model";
import { PRIORITY_THRESHOLDS, rankPatients } from "../episode/priority";
import { authorLine, professionalById } from "../episode/record";
import { PatientPriorityList } from "./PatientPriorityList";
import { PatientStatusCard } from "./PatientStatusCard";
import { SnapshotView } from "./SnapshotView";

const DEFAULT_ACTOR = "prof-nurse-day";
type Team = Pick<EpisodeRecord, "professionals">;

export function HandoffPage({ search }: { search: HandoffSearch }) {
  const { data: records, isPending, error } = useEpisodeRecords();

  return (
    <ModulePage stepId="handoff" connected>
      {isPending ? (
        <Flex justify="center" py="6"><Spinner size="3" /></Flex>
      ) : !records?.[0]?.professionals.length ? (
        <EmptyState title="Sin equipo" description={error?.message ?? "No se pudo cargar el equipo de demostración."} />
      ) : (
        <HandoffWorkspace records={records} team={records[0]} search={search} />
      )}
    </ModulePage>
  );
}

function HandoffWorkspace({ records, team, search }: { records: EpisodeRecord[]; team: Team; search: HandoffSearch }) {
  const navigate = useNavigate();
  const reset = useResetDemo();
  const actorId = professionalById(team, search.as ?? DEFAULT_ACTOR)?.id ?? team.professionals[0].id;
  const handoffs = useHandoffs(actorId);
  const tab = search.tab ?? "send";
  const received = handoffs.data?.filter(({ toId }) => toId === actorId) ?? [];
  const sent = handoffs.data?.filter(({ fromId }) => fromId === actorId) ?? [];
  const go = (patch: Partial<HandoffSearch>) =>
    navigate({ to: "/handoff", search: { as: actorId, tab, ...patch } });

  return (
    <Flex direction="column" gap="4">
      <Callout.Root color="gray" variant="surface">
        <Flex align="center" justify="between" gap="3" wrap="wrap">
          <Callout.Text>Profesionales y pacientes ficticios · datos de demostración.</Callout.Text>
          <Button variant="soft" color="gray" size="1" loading={reset.isPending}
            onClick={() => reset.mutate(undefined, { onSuccess: () => go({ handoff: undefined }) })}
          >
            Restablecer demo
          </Button>
        </Flex>
      </Callout.Root>

      <Flex direction="column" gap="1">
        <Text size="2" weight="medium">Actuando como (profesional demo)</Text>
        <Select.Root value={actorId} onValueChange={(as) => go({ as, handoff: undefined })}>
          <Select.Trigger aria-label="Profesional demo" style={{ maxWidth: 320 }} />
          <Select.Content>
            {team.professionals.map((professional) => (
              <Select.Item key={professional.id} value={professional.id}>
                {professional.name} · {professional.role}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </Flex>

      <Tabs.Root value={tab} onValueChange={(value) => go({ tab: value as HandoffTab, handoff: undefined })}>
        <Tabs.List>
          <Tabs.Trigger value="send">Nuevo traspaso</Tabs.Trigger>
          <Tabs.Trigger value="received">Recibidos ({received.length})</Tabs.Trigger>
          <Tabs.Trigger value="sent">Enviados ({sent.length})</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="send" mt="4">
          <SendHandoff
            key={actorId}
            records={records}
            team={team}
            actorId={actorId}
            onOpenReceived={(handoff) => go({ as: handoff.toId, tab: "received", handoff: handoff.id })}
          />
        </Tabs.Content>
        {(tab === "received" || tab === "sent") && (
          <Tabs.Content value={tab} mt="4">
            {handoffs.isPending ? (
              <Flex justify="center" py="6"><Spinner size="3" /></Flex>
            ) : handoffs.error ? (
              <EmptyState title="No se pudieron cargar las entregas" description={handoffs.error.message} />
            ) : (
              <HandoffInbox
                records={records}
                team={team}
                actorId={actorId}
                handoffs={tab === "received" ? received : sent}
                direction={tab}
                selectedId={search.handoff}
                onSelect={(handoff) => go({ handoff })}
              />
            )}
          </Tabs.Content>
        )}
      </Tabs.Root>
    </Flex>
  );
}

interface SendHandoffProps {
  records: EpisodeRecord[];
  team: Team;
  actorId: string;
  onOpenReceived: (handoff: Handoff) => void;
}

function SendHandoff({ records, team, actorId, onOpenReceived }: SendHandoffProps) {
  const recipients = team.professionals.filter((professional) => professional.id !== actorId);
  const [toId, setToId] = useState(recipients.find(({ discipline }) => discipline === "kinesiology")?.id ?? "");
  const [note, setNote] = useState("");
  const send = useSendHandoff();
  const snapshots = useMemo(() => buildHandoffSnapshots(records, actorId), [records, actorId]);
  const recipient = professionalById(team, toId);

  if (snapshots.length === 0) {
    return <EmptyState title="Sin pacientes para traspasar" description="Este profesional no tiene atenciones registradas al corte." />;
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
                <Button disabled={!recipient} loading={send.isPending}>Enviar traspaso</Button>
              </AlertDialog.Trigger>
              <AlertDialog.Content maxWidth="440px">
                <AlertDialog.Title>Confirmar traspaso</AlertDialog.Title>
                <AlertDialog.Description size="2">
                  Se enviará a {recipient?.name} una sola entrega con {patientCount(snapshots.length)}.
                </AlertDialog.Description>
                <Flex gap="3" mt="4" justify="end">
                  <AlertDialog.Cancel><Button variant="soft" color="gray">Cancelar</Button></AlertDialog.Cancel>
                  <AlertDialog.Action>
                    <Button onClick={() => send.mutate({ fromId: actorId, toId, note }, { onSuccess: () => setNote("") })}>
                      Confirmar envío
                    </Button>
                  </AlertDialog.Action>
                </Flex>
              </AlertDialog.Content>
            </AlertDialog.Root>
          </Flex>
          <Text size="1" color="gray">
            Incluye {snapshots.length === 1 ? "al paciente atendido" : `a los ${snapshots.length} pacientes atendidos`} por{" "}
            {authorLine(team, actorId)}.
          </Text>
          {send.error && (
            <Callout.Root color="red"><Callout.Text>{send.error.message}</Callout.Text></Callout.Root>
          )}
          {send.data && !send.isPending && (
            <Callout.Root color="green">
              <Flex align="center" justify="between" gap="2" wrap="wrap">
                <Callout.Text>Traspaso enviado a {professionalById(team, send.data.toId)?.name}.</Callout.Text>
                <Button size="1" variant="soft" onClick={() => onOpenReceived(send.data)}>
                  Abrir vista receptora
                </Button>
              </Flex>
            </Callout.Root>
          )}
        </Flex>
      </Card>
      <PatientSnapshots records={records} team={team} snapshots={snapshots} actorId={actorId} />
    </Flex>
  );
}

interface InboxProps {
  records: EpisodeRecord[];
  team: Team;
  actorId: string;
  handoffs: Handoff[];
  direction: "received" | "sent";
  selectedId: string | undefined;
  onSelect: (handoffId: string) => void;
}

function HandoffInbox({ records, team, actorId, handoffs, direction, selectedId, onSelect }: InboxProps) {
  if (handoffs.length === 0) {
    return (
      <EmptyState
        title={direction === "received" ? "Sin traspasos recibidos" : "Sin traspasos enviados"}
        description="Cambia de profesional demo o prepara una entrega desde «Nuevo traspaso»."
      />
    );
  }
  const selected = handoffs.find((handoff) => handoff.id === selectedId) ?? handoffs[0];

  return (
    <Flex direction="column" gap="4">
      {handoffs.length > 1 && (
        <Flex gap="2" wrap="wrap" role="group" aria-label="Entregas">
          {handoffs.map((handoff) => (
            <Button
              key={handoff.id}
              size="1"
              color="gray"
              variant={handoff.id === selected.id ? "soft" : "ghost"}
              aria-pressed={handoff.id === selected.id}
              onClick={() => onSelect(handoff.id)}
            >
              {direction === "received" ? "De " : "Para "}
              {professionalById(team, direction === "received" ? handoff.fromId : handoff.toId)?.name} ·{" "}
              {formatClinicalTime(handoff.sentAt)}
            </Button>
          ))}
        </Flex>
      )}
      <Flex direction="column" gap="1">
        <Heading size="4">Traspaso de {patientCount(selected.snapshots.length)}</Heading>
        <Text size="2" color="gray">
          De {authorLine(team, selected.fromId)} para {authorLine(team, selected.toId)} · {formatClinicalTime(selected.sentAt)}
        </Text>
        {selected.note && <Text size="2">«{selected.note}»</Text>}
      </Flex>
      <PatientSnapshots
        key={selected.id}
        records={records}
        team={team}
        snapshots={selected.snapshots}
        actorId={direction === "received" ? actorId : undefined}
      />
    </Flex>
  );
}

function PatientSnapshots({ records, team, snapshots, actorId }: {
  records: EpisodeRecord[];
  team: Team;
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
  team: Team;
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
                onClick={() => close.mutate({ episodeId: record.episode.id, pendingId: pending.id, closedById: actorId })}
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
