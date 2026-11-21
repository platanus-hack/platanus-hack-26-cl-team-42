import { formatElapsed } from "./format";
import type { HandoffSnapshot } from "./model";

export const PRIORITY_THRESHOLDS = {
  /** Horas sin atención que activan cada nivel, inclusive. */
  criticalEncounterHours: 8,
  attentionEncounterHours: 4,
  /** Horas restantes para que un pendiente abierto requiera atención. */
  upcomingDueHours: 2,
} as const;

export type PriorityLevel = "critical" | "attention" | "routine";

export interface PriorityReason {
  level: Exclude<PriorityLevel, "routine">;
  text: string;
}

export interface PatientPriority {
  level: PriorityLevel;
  reasons: PriorityReason[];
  hoursSinceLastEncounter: number | null;
}

export function assessPriority(snapshot: HandoffSnapshot, referenceAt: string): PatientPriority {
  return assessSnapshot(snapshot, referenceAt).priority;
}

export function rankPatients(snapshots: readonly HandoffSnapshot[], referenceAt: string) {
  return snapshots
    .map((snapshot) => ({ snapshot, ...assessSnapshot(snapshot, referenceAt) }))
    .sort((a, b) =>
      severity[b.priority.level] - severity[a.priority.level]
      || (b.priority.hoursSinceLastEncounter ?? Number.MAX_VALUE) - (a.priority.hoursSinceLastEncounter ?? Number.MAX_VALUE)
      || b.overdueCount - a.overdueCount
      || a.snapshot.episodeLabel.localeCompare(b.snapshot.episodeLabel, "es"),
    )
    .map(({ snapshot, priority }, index) => ({ snapshot, priority, rank: index + 1 }));
}

const severity = { routine: 0, attention: 1, critical: 2 };
const millisecondsPerHour = 3_600_000;

function assessSnapshot(snapshot: HandoffSnapshot, referenceAt: string) {
  const referenceTime = Date.parse(referenceAt);
  const reasons: PriorityReason[] = [];
  const overdue: string[] = [];
  for (const pending of snapshot.pendings) {
    if (pending.status !== "open" || !pending.dueAt) continue;
    const hoursUntilDue = (Date.parse(pending.dueAt) - referenceTime) / millisecondsPerHour;
    if (hoursUntilDue <= 0) {
      overdue.push(pending.title);
    } else if (hoursUntilDue <= PRIORITY_THRESHOLDS.upcomingDueHours) {
      reasons.push({ level: "attention", text: `Vence en ${formatElapsed(referenceAt, pending.dueAt)}: ${pending.title}` });
    }
  }

  if (overdue.length) {
    const label = overdue.length === 1 ? "1 pendiente vencido" : `${overdue.length} pendientes vencidos`;
    reasons.unshift({ level: "critical", text: `${label}: ${overdue[0]}` });
  }

  const lastEncounterAt = snapshot.lastEncounter?.occurredAt;
  const hoursSinceLastEncounter = lastEncounterAt
    ? Math.max(0, (referenceTime - Date.parse(lastEncounterAt)) / millisecondsPerHour)
    : null;
  if (hoursSinceLastEncounter === null) {
    reasons.push({ level: "attention", text: "Sin atención registrada" });
  } else if (lastEncounterAt && hoursSinceLastEncounter >= PRIORITY_THRESHOLDS.attentionEncounterHours) {
    reasons.push({
      level: hoursSinceLastEncounter >= PRIORITY_THRESHOLDS.criticalEncounterHours ? "critical" : "attention",
      text: `Última atención hace ${formatElapsed(lastEncounterAt, referenceAt)}`,
    });
  }

  const conflicts = snapshot.openConflicts?.length ?? 0;
  if (conflicts) {
    reasons.push({
      level: "attention",
      text: conflicts === 1 ? "1 conflicto por revisar" : `${conflicts} conflictos por revisar`,
    });
  }

  reasons.sort((a, b) => severity[b.level] - severity[a.level]);
  const priority: PatientPriority = {
    level: reasons[0]?.level ?? "routine",
    reasons,
    hoursSinceLastEncounter,
  };
  return { priority, overdueCount: overdue.length };
}
