import { useId, type CSSProperties } from "react";
import { Badge, Card, Flex, Text } from "@radix-ui/themes";
import { formatClinicalTime, formatElapsed } from "../episode/format";
import type { rankPatients } from "../episode/priority";

export function PatientPriorityList({ patients, referenceAt, selectedId, onSelect }: {
  patients: ReturnType<typeof rankPatients>;
  referenceAt: string;
  selectedId: string;
  onSelect: (episodeId: string) => void;
}) {
  const listId = useId();
  return (
    <Flex direction="column" gap="2" role="group" aria-label="Pacientes del traspaso">
      <Text size="1" color="gray">
        Ordenados por prioridad de visita · referencia {formatClinicalTime(referenceAt)}
      </Text>
      {patients.map(({ snapshot, priority, rank }) => {
        const selected = snapshot.episodeId === selectedId;
        const { label, color } = levels[priority.level];
        const descriptionId = `${listId}-${rank}`;
        const style: CSSProperties & { "--card-background-color"?: string } = {
          cursor: "pointer",
          textAlign: "left",
          boxShadow: selected ? "0 0 0 2px var(--accent-9)" : undefined,
        };
        if (priority.level !== "routine") {
          style.border = `2px solid var(--${color}-9)`;
          style["--card-background-color"] = `var(--${color}-a2)`;
        }
        const lastEncounterAt = snapshot.lastEncounter?.occurredAt;
        const lastAttention = lastEncounterAt
          ? `Última atención hace ${formatElapsed(lastEncounterAt, referenceAt)}`
          : "Sin atención registrada";
        const [mainReason, ...otherReasons] = priority.reasons;

        const additionalReason = mainReason && mainReason.text !== lastAttention ? mainReason.text : undefined;
        const descriptionIds = [`${descriptionId}-level`, `${descriptionId}-attention`];
        if (additionalReason) descriptionIds.push(`${descriptionId}-reason`);

        return (
          <Card
            key={snapshot.episodeId}
            asChild
            variant={selected ? "classic" : "surface"}
            style={style}
          >
            <button
              type="button"
              aria-label={snapshot.episodeLabel}
              aria-describedby={descriptionIds.join(" ")}
              aria-pressed={selected}
              onClick={() => onSelect(snapshot.episodeId)}
            >
              <Flex as="span" direction="column" gap="1">
                <Flex as="span" align="center" gap="2" wrap="wrap">
                  <Text weight="medium">{rank}º · {snapshot.episodeLabel}</Text>
                  <Badge id={`${descriptionId}-level`} color={color} variant="soft">{label}</Badge>
                </Flex>
                <Text id={`${descriptionId}-attention`} size="2">
                  {lastAttention}
                  {mainReason?.text === lastAttention && otherReasons.length > 0 && ` · y ${otherReasons.length} más`}
                </Text>
                {additionalReason && (
                  <Text id={`${descriptionId}-reason`} size="2">
                    {additionalReason}{otherReasons.length > 0 && ` · y ${otherReasons.length} más`}
                  </Text>
                )}
              </Flex>
            </button>
          </Card>
        );
      })}
    </Flex>
  );
}

const levels = {
  critical: { label: "Prioridad alta", color: "red" },
  attention: { label: "Requiere atención", color: "amber" },
  routine: { label: "Rutina", color: "gray" },
} as const;
