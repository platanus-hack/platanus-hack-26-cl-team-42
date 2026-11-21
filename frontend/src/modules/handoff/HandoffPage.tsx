import { useMemo, useState } from "react";
import {
  AlertDialog,
  Badge,
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
  TextArea,
} from "@radix-ui/themes";
import { useNavigate } from "@tanstack/react-router";
import { EmptyState } from "../../components/EmptyState";
import { ModulePage } from "../../components/ModulePage";
import type { HandoffSearch, HandoffTab } from "../../routes/_authenticated/handoff";
import { useClosePending, useEpisodeRecords, useHandoffs, useResetDemo, useSendHandoff } from "../episode/api";
import { PendingStatusBadge } from "../episode/components";
import { formatClinicalTime } from "../episode/format";
import { buildHandoffSnapshots, handoffReferenceAt } from "../episode/handoff";
import type { EpisodeRecord, Handoff, HandoffSnapshot } from "../episode/model";
import { rankPatients } from "../episode/priority";
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
      <Callout.Root color="amber" variant="surface">
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
    <Grid columns={{ initial: "1", md: "2fr 3fr" }} gap="4" align="start">
      <Card>
        <Flex direction="column" gap="3">
          <Heading size="4">Destinatario y nota</Heading>
          <Text size="2" color="gray">Entrega {authorLine(team, actorId)}</Text>
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
          <TextArea
            aria-label="Nota de la entrega"
            placeholder="Nota para la persona que recibe el turno"
            rows={4}
            value={note}
            maxLength={1000}
            onChange={(event) => setNote(event.target.value)}
          />
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
          <Flex justify="end">
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
        </Flex>
      </Card>

      <Flex direction="column" gap="2">
        <Heading size="4">Pacientes que se incluirán</Heading>
        <Text size="2" color="gray">Se incluyen todos los pacientes atendidos por quien entrega.</Text>
        <PatientSnapshots records={records} team={team} snapshots={snapshots} actorId={actorId} />
      </Flex>
    </Grid>
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
    <Grid columns={{ initial: "1", md: "1fr 2fr" }} gap="4" align="start">
      <Flex direction="column" gap="2">
        {handoffs.map((handoff) => {
          const counterpart = direction === "received" ? handoff.fromId : handoff.toId;
          return (
            <Card key={handoff.id} asChild variant={handoff.id === selected.id ? "classic" : "surface"}
              style={{ cursor: "pointer", textAlign: "left" }}
            >
              <button type="button" onClick={() => onSelect(handoff.id)} aria-pressed={handoff.id === selected.id}>
                <Flex as="span" direction="column" gap="1">
                  <Text weight="medium">
                    {direction === "received" ? "De " : "Para "}{authorLine(team, counterpart)}
                  </Text>
                  <Text size="1" color="gray">
                    {patientCount(handoff.snapshots.length)} · {formatClinicalTime(handoff.sentAt)}
                  </Text>
                </Flex>
              </button>
            </Card>
          );
        })}
      </Flex>
      <Flex direction="column" gap="3">
        <Card>
          <Flex direction="column" gap="2">
            <Flex align="center" justify="between" gap="2" wrap="wrap">
              <Heading size="4">Traspaso de {patientCount(selected.snapshots.length)}</Heading>
              <Badge color="gray" variant="soft">{formatClinicalTime(selected.sentAt)}</Badge>
            </Flex>
            <Text size="2">De {authorLine(team, selected.fromId)} para {authorLine(team, selected.toId)}</Text>
            {selected.note && <Text size="2">{selected.note}</Text>}
          </Flex>
        </Card>
        <PatientSnapshots
          key={selected.id}
          records={records}
          team={team}
          snapshots={selected.snapshots}
          sent
          actorId={direction === "received" ? actorId : undefined}
        />
      </Flex>
    </Grid>
  );
}

function PatientSnapshots({ records, team, snapshots, sent = false, actorId }: {
  records: EpisodeRecord[];
  team: Team;
  snapshots: HandoffSnapshot[];
  sent?: boolean;
  actorId?: string;
}) {
  const [episodeId, setEpisodeId] = useState<string>();
  const referenceAt = handoffReferenceAt(snapshots);
  const patients = referenceAt ? rankPatients(snapshots, referenceAt) : [];
  const snapshot = patients.find((item) => item.snapshot.episodeId === episodeId)?.snapshot ?? patients[0]?.snapshot;
  if (!snapshot || !referenceAt) return null;

  const record = records.find(({ episode }) => episode.id === snapshot.episodeId);

  return (
    <Flex direction="column" gap="3">
      <PatientPriorityList
        patients={patients}
        referenceAt={referenceAt}
        selectedId={snapshot.episodeId}
        onSelect={setEpisodeId}
      />
      <Text size="1" color="gray">Datos al {formatClinicalTime(snapshot.cutoffAt)}</Text>
      <PatientStatusCard team={team} snapshot={snapshot} referenceAt={referenceAt} />
      {actorId && record && <EpisodePendings key={record.episode.id} record={record} actorId={actorId} />}
      <SnapshotView record={team} snapshot={snapshot} currentPendings={sent ? record?.pendings : undefined} />
    </Flex>
  );
}

function EpisodePendings({ record, actorId }: { record: EpisodeRecord; actorId: string }) {
  const close = useClosePending();
  if (record.pendings.length === 0) return null;

  return (
    <Card>
      <Flex direction="column" gap="3">
        <Heading size="3">Pendientes del paciente (estado actual)</Heading>
        {close.error && (
          <Callout.Root color="red"><Callout.Text>{close.error.message}</Callout.Text></Callout.Root>
        )}
        {record.pendings.map((pending) => (
          <Flex key={pending.id} align="center" justify="between" gap="2">
            <Flex direction="column" gap="1">
              <Flex gap="2" align="center">
                <PendingStatusBadge status={pending.status} />
                <Text size="2">{pending.title}</Text>
              </Flex>
              <Text size="1" color="gray">
                {authorLine(record, pending.ownerId)}
                {pending.dueAt ? ` · plazo ${formatClinicalTime(pending.dueAt)}` : ""}
              </Text>
            </Flex>
            {pending.status === "open" && (
              <Button
                size="1"
                variant="soft"
                aria-label={`Cerrar pendiente: ${pending.title}`}
                disabled={close.isPending}
                loading={close.isPending && close.variables?.pendingId === pending.id}
                onClick={() => close.mutate({ episodeId: record.episode.id, pendingId: pending.id, closedById: actorId })}
              >
                Cerrar
              </Button>
            )}
          </Flex>
        ))}
      </Flex>
    </Card>
  );
}

function patientCount(count: number): string {
  return `${count} ${count === 1 ? "paciente" : "pacientes"}`;
}
