import type { ReactNode } from "react";
import { Badge, Card, Flex, Heading, Text, TextArea } from "@radix-ui/themes";
import { CopyButton, OpenConflicts, PendingStatusBadge, SourceLink } from "../episode/components";
import { formatClinicalTime } from "../episode/format";
import type { EpisodeRecord, HandoffSnapshot, PendingTask, SourcedEntry } from "../episode/model";
import { authorLine, datumText, ENTRY_KIND_LABEL } from "../episode/record";

interface SnapshotViewProps {
  record: Pick<EpisodeRecord, "professionals">;
  snapshot: HandoffSnapshot;
  /** Estado vivo de los pendientes, para señalar cambios posteriores al envío. */
  currentPendings?: PendingTask[];
}

/** Contenido de un traspaso: siempre se pinta desde la copia fija, nunca desde el estado vivo. */
export function SnapshotView({ record, snapshot, currentPendings }: SnapshotViewProps) {
  return (
    <Flex direction="column" gap="3">
      <OpenConflicts episodeId={snapshot.episodeId} conflicts={snapshot.openConflicts ?? []} />
      <Section title="Cambios recientes" empty="Sin cambios en las últimas horas antes del corte.">
        {snapshot.recentChanges.map((entry) => (
          <EntryLine key={entry.entryId} record={record} entry={entry} episodeId={snapshot.episodeId} showKind />
        ))}
      </Section>

      <Section title="Plan vigente validado" empty="Sin plan validado.">
        {snapshot.plan.map((entry) => (
          <EntryLine key={entry.entryId} record={record} entry={entry} episodeId={snapshot.episodeId} />
        ))}
      </Section>

      <Section title="Datos al corte" empty="Sin mediciones.">
        {snapshot.cutoffData.map((datum) => (
          <Flex key={datum.code} direction="column">
            <Text size="2" weight="medium">
              {datumText(datum)}
            </Text>
            <Text size="1" color="gray">
              {formatClinicalTime(datum.observedAt)} · {authorLine(record, datum.source.authorId)} ·{" "}
              <SourceLink episodeId={snapshot.episodeId} encounterId={datum.source.encounterId}>
                ver atención de origen
              </SourceLink>
            </Text>
          </Flex>
        ))}
      </Section>

      <Section title="Pendientes (estado al enviar)" empty="Sin pendientes.">
        {snapshot.pendings.map((pending) => {
          const current = currentPendings?.find((item) => item.id === pending.id);
          return (
            <Flex key={pending.id} direction="column" gap="1">
              <Flex gap="2" align="center" wrap="wrap">
                <PendingStatusBadge status={pending.status} />
                <Text size="2">{pending.title}</Text>
                {current && current.status !== pending.status && (
                  <Badge color="gray" variant="outline">
                    Ahora: {current.status === "done" ? "cerrado" : "abierto"}
                  </Badge>
                )}
              </Flex>
              <Text size="1" color="gray">
                Responsable {authorLine(record, pending.ownerId)}
                {pending.dueAt ? ` · plazo ${formatClinicalTime(pending.dueAt)}` : " · sin plazo"} ·{" "}
                <SourceLink episodeId={snapshot.episodeId} encounterId={pending.sourceEncounterId}>
                  ver atención de origen
                </SourceLink>
              </Text>
            </Flex>
          );
        })}
      </Section>

      <Card>
        <Flex direction="column" gap="2">
          <Flex align="center" justify="between" gap="2">
            <Heading size="3">Resumen en texto</Heading>
            <CopyButton text={snapshot.summaryText} label="Copiar resumen" />
          </Flex>
          <TextArea
            readOnly
            value={snapshot.summaryText}
            rows={10}
            aria-label="Resumen del traspaso"
            style={{ fontFamily: "var(--code-font-family)" }}
          />
        </Flex>
      </Card>
    </Flex>
  );
}

function Section({ title, empty, children }: { title: string; empty: string; children: ReactNode[] }) {
  return (
    <Card>
      <Flex direction="column" gap="2">
        <Heading size="3">{title}</Heading>
        {children.length === 0 ? (
          <Text size="2" color="gray">
            {empty}
          </Text>
        ) : (
          children
        )}
      </Flex>
    </Card>
  );
}

function EntryLine({
  record,
  entry,
  episodeId,
  showKind = false,
}: {
  record: Pick<EpisodeRecord, "professionals">;
  entry: SourcedEntry;
  episodeId: string;
  showKind?: boolean;
}) {
  return (
    <Flex direction="column">
      <Text size="2">
        {showKind && <Badge variant="surface" mr="2">{ENTRY_KIND_LABEL[entry.kind]}</Badge>}
        {entry.text}
      </Text>
      <Text size="1" color="gray">
        {authorLine(record, entry.authorId)} · {formatClinicalTime(entry.occurredAt)} ·{" "}
        <SourceLink episodeId={episodeId} encounterId={entry.encounterId}>ver atención de origen</SourceLink>
      </Text>
    </Flex>
  );
}
