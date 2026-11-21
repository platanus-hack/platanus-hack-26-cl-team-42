import type { CSSProperties } from "react";
import { Card, Flex, Text } from "@radix-ui/themes";
import { formatClinicalTime, formatElapsed } from "../episode/format";
import type { PriorityLevel, rankPatients } from "../episode/priority";

/**
 * Lista de pacientes en orden de visita. El color se reserva para la urgencia
 * (franja lateral y etiqueta); la selección es neutra para no competir con ella.
 */
export function PatientPriorityList({ patients, referenceAt, selectedId, onSelect }: {
  patients: ReturnType<typeof rankPatients>;
  referenceAt: string;
  selectedId: string;
  onSelect: (episodeId: string) => void;
}) {
  return (
    <Flex direction="column" gap="2">
      <Text size="1" color="gray">Orden de visita · corte {formatClinicalTime(referenceAt)}</Text>
      <Flex direction="column" gap="2" role="group" aria-label="Pacientes del traspaso">
        {patients.map(({ snapshot, priority, rank }) => {
          const selected = snapshot.episodeId === selectedId;
          const level = LEVELS[priority.level];
          const lastEncounterAt = snapshot.lastEncounter?.occurredAt;
          const elapsed = lastEncounterAt ? `hace ${formatElapsed(lastEncounterAt, referenceAt)}` : "sin atención registrada";
          const detail = priority.reasons.find(({ text }) => !text.startsWith("Última atención") && text !== "Sin atención registrada");
          const style: CSSProperties & Record<"--card-background-color", string | undefined> = {
            cursor: "pointer",
            textAlign: "left",
            "--card-background-color": selected ? "var(--gray-a3)" : undefined,
          };

          return (
            <Card key={snapshot.episodeId} asChild size="1" style={style}>
              <button
                type="button"
                aria-label={snapshot.episodeLabel}
                aria-pressed={selected}
                onClick={() => onSelect(snapshot.episodeId)}
              >
                {level.color && <span aria-hidden style={stripe(level.color)} />}
                <Flex as="span" gap="3" align="start" pl="1">
                  <Text size="5" weight="bold" color="gray" style={{ minWidth: "1.25em" }}>{rank}</Text>
                  <Flex as="span" direction="column" gap="1" minWidth="0">
                    <Text size="2" weight={selected ? "bold" : "medium"}>{snapshot.episodeLabel}</Text>
                    <Text size="1">
                      {level.color && <Text color={level.color} weight="medium">● {level.label} · </Text>}
                      <Text color="gray">{level.color ? elapsed : `${level.label} · ${elapsed}`}</Text>
                    </Text>
                    {detail && <Text size="1" color="gray" truncate>{detail.text}</Text>}
                  </Flex>
                </Flex>
              </button>
            </Card>
          );
        })}
      </Flex>
    </Flex>
  );
}

const LEVELS: Record<PriorityLevel, { label: string; color?: "red" | "amber" }> = {
  critical: { label: "Prioridad alta", color: "red" },
  attention: { label: "Requiere atención", color: "amber" },
  routine: { label: "Rutina" },
};

function stripe(color: "red" | "amber"): CSSProperties {
  return { position: "absolute", insetBlock: 0, left: 0, width: 4, background: `var(--${color}-9)` };
}
