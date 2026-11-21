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
import { Link, useNavigate } from "@tanstack/react-router";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { useClosePending, useEpisodeRecord, useHandoffs, useResetDemo, useSendHandoff } from "../episode/api";
import { DemoEpisodeBanner, PendingStatusBadge } from "../episode/components";
import { DEMO_EPISODE_ID } from "../episode/fixture";
import { formatClinicalTime } from "../episode/format";
import { buildHandoffSnapshot } from "../episode/handoff";
import type { EpisodeRecord, Handoff } from "../episode/model";
import { authorLine, professionalById } from "../episode/record";
import type { HandoffSearch, HandoffTab } from "../../routes/_authenticated/handoff";
import { SnapshotView } from "./SnapshotView";

/** Profesional demo por defecto: la enfermera del turno de día que entrega. */
const DEFAULT_ACTOR = "prof-nurse-day";

export function HandoffPage({ search }: { search: HandoffSearch }) {
  const record = useEpisodeRecord(DEMO_EPISODE_ID);
  const handoffs = useHandoffs(DEMO_EPISODE_ID);

  return (
    <ModulePage stepId="handoff" connected>
      {record.isPending || handoffs.isPending ? (
        <Flex justify="center" py="6">
          <Spinner size="3" />
        </Flex>
      ) : !record.data || !handoffs.data ? (
        <EmptyState
          title="Sin episodio"
          description={(record.error ?? handoffs.error)?.message ?? "No se pudo cargar el episodio de demostración."}
        />
      ) : (
        <HandoffWorkspace record={record.data} handoffs={handoffs.data} search={search} />
      )}
    </ModulePage>
  );
}

interface WorkspaceProps {
  record: EpisodeRecord;
  handoffs: Handoff[];
  search: HandoffSearch;
}

function HandoffWorkspace({ record, handoffs, search }: WorkspaceProps) {
  const navigate = useNavigate();
  const reset = useResetDemo();
  const actorId = professionalById(record, search.as)?.id ?? DEFAULT_ACTOR;
  const tab = search.tab ?? "send";
  const received = handoffs.filter((handoff) => handoff.toId === actorId);
  const sent = handoffs.filter((handoff) => handoff.fromId === actorId);
  const go = (patch: Partial<HandoffSearch>) =>
    navigate({ to: "/handoff", search: { as: actorId, tab, ...patch } });

  return (
    <Flex direction="column" gap="4">
      <DemoEpisodeBanner episode={record.episode}>
        <Button
          variant="soft"
          color="gray"
          size="1"
          loading={reset.isPending}
          onClick={() => reset.mutate(record.episode.id, { onSuccess: () => go({ handoff: undefined }) })}
        >
          Restablecer demo
        </Button>
      </DemoEpisodeBanner>

      <Flex direction="column" gap="1">
        <Text size="2" weight="medium">
          Actuando como (profesional demo)
        </Text>
        <Select.Root value={actorId} onValueChange={(as) => go({ as, handoff: undefined })}>
          <Select.Trigger aria-label="Profesional demo" style={{ maxWidth: 320 }} />
          <Select.Content>
            {record.professionals.map((professional) => (
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
            record={record}
            actorId={actorId}
            onOpenReceived={(handoff) => go({ as: handoff.toId, tab: "received", handoff: handoff.id })}
          />
        </Tabs.Content>
        <Tabs.Content value="received" mt="4">
          <HandoffInbox
            record={record}
            handoffs={received}
            direction="received"
            selectedId={search.handoff}
            onSelect={(handoff) => go({ handoff })}
          />
          {received.length > 0 && (
            <Flex mt="4" direction="column">
              <EpisodePendings record={record} actorId={actorId} />
            </Flex>
          )}
        </Tabs.Content>
        <Tabs.Content value="sent" mt="4">
          <HandoffInbox
            record={record}
            handoffs={sent}
            direction="sent"
            selectedId={search.handoff}
            onSelect={(handoff) => go({ handoff })}
          />
        </Tabs.Content>
      </Tabs.Root>
    </Flex>
  );
}

interface SendHandoffProps {
  record: EpisodeRecord;
  actorId: string;
  onOpenReceived: (handoff: Handoff) => void;
}

function SendHandoff({ record, actorId, onOpenReceived }: SendHandoffProps) {
  const recipients = record.professionals.filter((professional) => professional.id !== actorId);
  const [toId, setToId] = useState(
    recipients.find((professional) => professional.discipline === "kinesiology")?.id ?? "",
  );
  const [note, setNote] = useState("");
  const send = useSendHandoff();
  const preview = useMemo(() => buildHandoffSnapshot(record), [record]);
  const recipient = professionalById(record, toId);

  const confirm = () => {
    if (!toId) return;
    send.mutate(
      { episodeId: record.episode.id, fromId: actorId, toId, note },
      { onSuccess: () => setNote("") },
    );
  };

  return (
    <Grid columns={{ initial: "1", md: "2fr 3fr" }} gap="4" align="start">
      <Flex direction="column" gap="4">
        <Card>
          <Flex direction="column" gap="3">
            <Heading size="4">Destinatario y nota</Heading>
            <Text size="2" color="gray">
              Entrega {authorLine(record, actorId)}
            </Text>
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
              placeholder="Nota para la persona que recibe el caso"
              rows={4}
              value={note}
              maxLength={1000}
              onChange={(event) => setNote(event.target.value)}
            />
            {send.error && (
              <Callout.Root color="red">
                <Callout.Text>{send.error.message}</Callout.Text>
              </Callout.Root>
            )}
            {send.data && !send.isPending && (
              <Callout.Root color="green">
                <Flex align="center" justify="between" gap="2" wrap="wrap">
                  <Callout.Text>Traspaso enviado a {professionalById(record, send.data.toId)?.name}.</Callout.Text>
                  <Button size="1" variant="soft" onClick={() => onOpenReceived(send.data)}>
                    Abrir vista receptora
                  </Button>
                </Flex>
              </Callout.Root>
            )}
            <Flex justify="end">
              <AlertDialog.Root>
                <AlertDialog.Trigger>
                  <Button disabled={!recipient} loading={send.isPending}>
                    Traspasar caso
                  </Button>
                </AlertDialog.Trigger>
                <AlertDialog.Content maxWidth="440px">
                  <AlertDialog.Title>Confirmar traspaso</AlertDialog.Title>
                  <AlertDialog.Description size="2">
                    Se enviará a {recipient ? authorLine(record, recipient.id) : "—"} una copia fija del resumen,
                    {` ${preview.recentChanges.length}`} cambios recientes, {preview.cutoffData.length} datos al corte y{" "}
                    {preview.pendings.length} pendientes con su estado actual.
                  </AlertDialog.Description>
                  <Flex gap="3" mt="4" justify="end">
                    <AlertDialog.Cancel>
                      <Button variant="soft" color="gray">
                        Cancelar
                      </Button>
                    </AlertDialog.Cancel>
                    <AlertDialog.Action>
                      <Button onClick={confirm}>Confirmar envío</Button>
                    </AlertDialog.Action>
                  </Flex>
                </AlertDialog.Content>
              </AlertDialog.Root>
            </Flex>
          </Flex>
        </Card>
        <EpisodePendings record={record} actorId={actorId} />
      </Flex>

      <Flex direction="column" gap="2">
        <Heading size="4">Vista previa de lo que se enviará</Heading>
        <SnapshotView record={record} snapshot={preview} />
      </Flex>
    </Grid>
  );
}

/** Estado vivo de los pendientes. Cerrar uno es una acción aparte del traspaso. */
function EpisodePendings({ record, actorId }: { record: EpisodeRecord; actorId: string }) {
  const close = useClosePending();
  return (
    <Card>
      <Flex direction="column" gap="3">
        <Heading size="3">Pendientes del episodio (estado actual)</Heading>
        {close.error && (
          <Callout.Root color="red">
            <Callout.Text>{close.error.message}</Callout.Text>
          </Callout.Root>
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
                onClick={() =>
                  close.mutate({ episodeId: record.episode.id, pendingId: pending.id, closedById: actorId })
                }
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

interface InboxProps {
  record: EpisodeRecord;
  handoffs: Handoff[];
  direction: "received" | "sent";
  selectedId: string | undefined;
  onSelect: (handoffId: string) => void;
}

function HandoffInbox({ record, handoffs, direction, selectedId, onSelect }: InboxProps) {
  if (handoffs.length === 0) {
    return (
      <EmptyState
        title={direction === "received" ? "Sin traspasos recibidos" : "Sin traspasos enviados"}
        description="Cambia de profesional demo o envía un traspaso desde «Nuevo traspaso»."
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
            <Card
              key={handoff.id}
              asChild
              variant={handoff.id === selected.id ? "classic" : "surface"}
              style={{ cursor: "pointer", textAlign: "left" }}
            >
              <button type="button" onClick={() => onSelect(handoff.id)} aria-pressed={handoff.id === selected.id}>
                <Flex as="span" direction="column" gap="1">
                  <Text weight="medium">
                    {direction === "received" ? "De " : "Para "}
                    {authorLine(record, counterpart)}
                  </Text>
                  <Text size="1" color="gray">
                    Enviado {formatClinicalTime(handoff.sentAt)}
                  </Text>
                </Flex>
              </button>
            </Card>
          );
        })}
      </Flex>
      <HandoffDetail record={record} handoff={selected} />
    </Grid>
  );
}

function HandoffDetail({ record, handoff }: { record: EpisodeRecord; handoff: Handoff }) {
  return (
    <Flex direction="column" gap="3">
      <Card>
        <Flex direction="column" gap="2">
          <Flex align="center" justify="between" gap="2" wrap="wrap">
            <Heading size="4">Traspaso</Heading>
            <Badge color="gray" variant="soft">
              Copia fija · {formatClinicalTime(handoff.sentAt)}
            </Badge>
          </Flex>
          <Text size="2">
            De {authorLine(record, handoff.fromId)} para {authorLine(record, handoff.toId)}
          </Text>
          <Text size="2" color={handoff.note ? undefined : "gray"}>
            {handoff.note ? `Nota: ${handoff.note}` : "Sin nota."}
          </Text>
          <Text size="1" color="gray">
            Copia del episodio al corte {formatClinicalTime(handoff.snapshot.cutoffAt)}. Los enlaces abren la atención
            de origen en el <Link to="/official-form">registro clínico</Link>.
          </Text>
        </Flex>
      </Card>
      <SnapshotView record={record} snapshot={handoff.snapshot} currentPendings={record.pendings} />
    </Flex>
  );
}
