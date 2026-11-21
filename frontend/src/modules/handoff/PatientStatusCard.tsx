import { Flex, Heading, Text } from "@radix-ui/themes";
import { formatClinicalTime } from "../episode/format";
import type { EpisodeRecord, HandoffSnapshot } from "../episode/model";
import { authorLine } from "../episode/record";
import { summarizePatientStatus, type PatientVital } from "../episode/status";

interface PatientStatusCardProps {
  team: Pick<EpisodeRecord, "professionals">;
  snapshot: HandoffSnapshot;
  referenceAt: string;
}

/**
 * Cabecera del paciente seleccionado: quién lo vio por última vez y sus signos
 * al corte en una línea. Solo los valores fuera de rango llevan color.
 */
export function PatientStatusCard({ team, snapshot, referenceAt }: PatientStatusCardProps) {
  const { lastEncounter, vitals } = summarizePatientStatus(snapshot, referenceAt);

  return (
    <Flex direction="column" gap="1" role="region" aria-label="Estado al corte">
      <Heading size="4">{snapshot.episodeLabel}</Heading>
      <Text size="2" color="gray">
        {lastEncounter
          ? `Última atención ${formatClinicalTime(lastEncounter.occurredAt)} · ${authorLine(team, lastEncounter.authorId)} · hace ${lastEncounter.elapsed}`
          : "Sin atención registrada"}
      </Text>
      {vitals.length > 0 && (
        <Flex gap="4" wrap="wrap" mt="1" aria-label="Signos al corte" role="list">
          {vitals.map((vital) => (
            <Vital key={vital.code} vital={vital} lastEncounterAt={lastEncounter?.occurredAt} />
          ))}
        </Flex>
      )}
    </Flex>
  );
}

function Vital({ vital, lastEncounterAt }: { vital: PatientVital; lastEncounterAt?: string }) {
  const stale = lastEncounterAt && Date.parse(vital.observedAt) < Date.parse(lastEncounterAt);
  const flag = VITAL_FLAG[vital.flag];

  return (
    <Text size="2" role="listitem">
      <Text color="gray">{vital.label} </Text>
      <Text weight="bold" color={flag?.color}>{vital.value} {vital.unit}</Text>
      {flag && <Text size="1" color={flag.color}> {flag.label}</Text>}
      {stale && <Text size="1" color="gray"> · {formatClinicalTime(vital.observedAt)}</Text>}
    </Text>
  );
}

const VITAL_FLAG: Partial<Record<PatientVital["flag"], { label: string; color: "amber" | "gray" }>> = {
  low: { label: "↓ bajo", color: "amber" },
  high: { label: "↑ alto", color: "amber" },
  unknown: { label: "sin rango", color: "gray" },
};
