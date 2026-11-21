import { formatElapsed } from "./format";
import type { CutoffDatum, HandoffSnapshot, PendingTask } from "./model";

export type VitalFlag = "low" | "high" | "normal" | "unknown";

export type PatientVital = Pick<CutoffDatum, "code" | "label" | "value" | "unit" | "observedAt"> & {
  flag: VitalFlag;
};

export interface PatientStatus {
  lastEncounter: { occurredAt: string; authorId: string; elapsed: string } | null;
  pendings: { open: number; overdue: number; nextDue: PendingTask | null };
  openConflicts: number;
  vitals: PatientVital[];
}

// Rangos orientativos para adultos, con límites inclusivos. Son una ayuda visual
// y no constituyen un diagnóstico. PA se evalúa por su valor sistólico.
export const ADULT_VITAL_RANGES = {
  spo2: { min: 92, max: 100 },
  hr: { min: 60, max: 100 },
  rr: { min: 12, max: 20 },
  temp: { min: 36, max: 37.9 },
  sbp: { min: 90, max: 120 },
  pa: { min: 90, max: 120 },
} as const;

export function summarizePatientStatus(snapshot: HandoffSnapshot, referenceAt: string): PatientStatus {
  const { lastEncounter } = snapshot;

  return {
    lastEncounter: lastEncounter ? {
      occurredAt: lastEncounter.occurredAt,
      authorId: lastEncounter.authorId,
      elapsed: formatElapsed(lastEncounter.occurredAt, referenceAt),
    } : null,
    pendings: summarizePendings(snapshot.pendings, Date.parse(referenceAt)),
    openConflicts: snapshot.openConflicts?.length ?? 0,
    vitals: snapshot.cutoffData.filter(isKnownVital).map(summarizeVital),
  };
}

function summarizePendings(pendings: PendingTask[], referenceTime: number): PatientStatus["pendings"] {
  let open = 0;
  let overdue = 0;
  let nextDue: PendingTask | null = null;
  let nextDueTime = Infinity;

  for (const pending of pendings) {
    if (pending.status !== "open") continue;
    open++;
    if (!pending.dueAt) continue;

    const dueTime = Date.parse(pending.dueAt);
    if (dueTime <= referenceTime) {
      overdue++;
    } else if (dueTime > referenceTime && dueTime < nextDueTime) {
      nextDue = pending;
      nextDueTime = dueTime;
    }
  }

  return { open, overdue, nextDue };
}

function isKnownVital(datum: CutoffDatum): datum is CutoffDatum & { code: keyof typeof ADULT_VITAL_RANGES } {
  return Object.hasOwn(ADULT_VITAL_RANGES, datum.code);
}

function summarizeVital({ code, label, value, unit, observedAt }: CutoffDatum & {
  code: keyof typeof ADULT_VITAL_RANGES;
}): PatientVital {
  return { code, label, value, unit, observedAt, flag: vitalFlag(code, value) };
}

function vitalFlag(code: keyof typeof ADULT_VITAL_RANGES, value: string): VitalFlag {
  const normalized = value.trim().replaceAll(",", ".");
  const match = code === "pa"
    ? /^(\d+(?:\.\d+)?)(?:\s*\/\s*\d+(?:\.\d+)?)?$/.exec(normalized)
    : /^([+-]?\d+(?:\.\d+)?)$/.exec(normalized);
  if (!match) return "unknown";

  const measured = Number(match[1]);
  if (!Number.isFinite(measured)) return "unknown";
  const { min, max } = ADULT_VITAL_RANGES[code];
  if (measured < min) return "low";
  if (measured > max) return "high";
  return "normal";
}
