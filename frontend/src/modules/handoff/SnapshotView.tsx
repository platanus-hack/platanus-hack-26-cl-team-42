import type { ReactNode } from "react";
import { Badge, Flex, Text, TextArea } from "@radix-ui/themes";
import { CopyButton, SourceLink } from "../episode/components";
import { formatClinicalTime } from "../episode/format";
import type { EpisodeRecord, HandoffSnapshot, SourcedEntry } from "../episode/model";
import { authorLine, datumText, ENTRY_KIND_LABEL } from "../episode/record";

interface SnapshotViewProps {
  record: Pick<EpisodeRecord, "professionals">;
  snapshot: HandoffSnapshot;
}

/**
 * Detalle de lectura del traspaso, plegado por defecto: lo urgente (pendientes,
 * conflictos, signos) ya está arriba. Se pinta desde la copia fija, nunca desde
 * el estado vivo.
 */
export function SnapshotView({ record, snapshot }: SnapshotViewProps) {
  return (
    <Flex direction="column" style={{ borderTop: "1px solid var(--gray-a5)" }}>
      <Section title="Cambios recientes" count={snapshot.recentChanges.length} empty="Sin cambios en las últimas horas antes del corte.">
        {snapshot.recentChanges.map((entry) => (
          <EntryLine key={entry.entryId} record={record} entry={entry} episodeId={snapshot.episodeId} showKind />
        ))}
      </Section>

      <Section title="Plan vigente validado" count={snapshot.plan.length} empty="Sin plan validado.">
        {snapshot.plan.map((entry) => (
          <EntryLine key={entry.entryId} record={record} entry={entry} episodeId={snapshot.episodeId} />
        ))}
      </Section>

      <Section title="Datos al corte y su origen" count={snapshot.cutoffData.length} empty="Sin mediciones.">
        {snapshot.cutoffData.map((datum) => (
          <Flex key={datum.code} direction="column">
            <Text size="2">{datumText(datum)}</Text>
            <Text size="1" color="gray">
              {formatClinicalTime(datum.observedAt)} · {authorLine(record, datum.source.authorId)} ·{" "}
              <SourceLink episodeId={snapshot.episodeId} encounterId={datum.source.encounterId}>
                ver atención de origen
              </SourceLink>
            </Text>
          </Flex>
        ))}
      </Section>

      <Section title="Resumen en texto">
        <Flex direction="column" gap="2" align="end">
          <TextArea
            readOnly
            value={snapshot.summaryText}
            rows={10}
            aria-label="Resumen del traspaso"
            style={{ fontFamily: "var(--code-font-family)", width: "100%" }}
          />
          <CopyButton text={snapshot.summaryText} label="Copiar resumen" />
        </Flex>
      </Section>
    </Flex>
  );
}

function Section({ title, count, empty, children }: {
  title: string;
  count?: number;
  empty?: string;
  children: ReactNode;
}) {
  return (
    <details style={{ borderBottom: "1px solid var(--gray-a5)" }}>
      <summary style={{ cursor: "pointer", padding: "var(--space-3) 0" }}>
        <Text size="2" weight="medium">{title}</Text>
        {count !== undefined && <Text size="2" color="gray"> · {count}</Text>}
      </summary>
      <Flex direction="column" gap="2" pb="3">
        {count === 0 ? <Text size="2" color="gray">{empty}</Text> : children}
      </Flex>
    </details>
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
