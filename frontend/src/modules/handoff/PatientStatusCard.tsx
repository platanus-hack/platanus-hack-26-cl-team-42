import { Badge, Card, Flex, Grid, Heading, Text } from "@radix-ui/themes";
import { formatClinicalTime } from "../episode/format";
import type { EpisodeRecord, HandoffSnapshot } from "../episode/model";
import { authorLine } from "../episode/record";
import { summarizePatientStatus, type PatientVital } from "../episode/status";

interface PatientStatusCardProps {
  team: Pick<EpisodeRecord, "professionals">;
  snapshot: HandoffSnapshot;
  referenceAt: string | undefined;
}

export function PatientStatusCard({ team, snapshot, referenceAt }: PatientStatusCardProps) {
  const { lastEncounter, pendings, openConflicts, vitals } = summarizePatientStatus(
    snapshot,
    referenceAt ?? snapshot.cutoffAt,
  );

  return (
    <Card role="region" aria-label="Estado al corte">
      <Flex direction="column" gap="2">
        <Heading size="3">Estado al corte</Heading>
        <Text size="2">
          {lastEncounter
            ? `Última atención hace ${lastEncounter.elapsed} · ${authorLine(team, lastEncounter.authorId)}`
            : "Sin atención registrada"}
        </Text>
        <Flex gap="2" wrap="wrap">
          <Badge color="gray">Pendientes abiertos: {pendings.open}</Badge>
          <Badge color={pendings.overdue > 0 ? "red" : "gray"}>Vencidos: {pendings.overdue}</Badge>
          {pendings.nextDue?.dueAt && (
            <Badge color="gray" style={{ whiteSpace: "normal" }}>
              Próximo: {pendings.nextDue.title} · {formatClinicalTime(pendings.nextDue.dueAt)}
            </Badge>
          )}
          <Badge color={openConflicts > 0 ? "amber" : "gray"}>Conflictos abiertos: {openConflicts}</Badge>
        </Flex>
        {vitals.length > 0 && (
          <Grid columns={{ initial: "2", sm: "3", lg: "4" }} gap="2">
            {vitals.map((vital) => (
              <VitalTile key={vital.code} vital={vital} lastEncounterAt={lastEncounter?.occurredAt} />
            ))}
          </Grid>
        )}
      </Flex>
    </Card>
  );
}

function VitalTile({ vital, lastEncounterAt }: { vital: PatientVital; lastEncounterAt?: string }) {
  const showObservedAt = lastEncounterAt && Date.parse(vital.observedAt) < Date.parse(lastEncounterAt);

  return (
    <Card size="1" variant="surface">
      <Flex direction="column" gap="1" align="start">
        <Text size="1" color="gray">{vital.label}</Text>
        <Text size="4" weight="bold">
          {vital.value} <Text size="1" weight="regular">{vital.unit}</Text>
        </Text>
        {vital.flag !== "normal" && (
          <Badge color={vital.flag === "unknown" ? "gray" : "amber"}>{VITAL_FLAG_LABEL[vital.flag]}</Badge>
        )}
        {showObservedAt && (
          <Text size="1" color="gray">Medición: {formatClinicalTime(vital.observedAt)}</Text>
        )}
      </Flex>
    </Card>
  );
}

const VITAL_FLAG_LABEL = {
  low: "Bajo el rango",
  high: "Sobre el rango",
  unknown: "Rango no evaluable",
};
