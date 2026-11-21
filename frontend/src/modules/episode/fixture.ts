import type { EpisodeRecord } from "./model";

/**
 * Episodio ficticio de demostración. Ningún dato proviene de grabaciones
 * reales ni de `patient_reference`: todo se une por `episode.id`.
 */
export const DEMO_EPISODE_ID = "demo-episode-001";
export const DEMO_SECOND_EPISODE_ID = "demo-episode-002";
export const DEMO_OTHER_EPISODE_ID = "demo-episode-003";

export const DEMO_EPISODE: EpisodeRecord = {
  episode: {
    id: DEMO_EPISODE_ID,
    isFictional: true,
    label: "Paciente ficticio DEMO-001 · Cama 12",
    unit: "Intermedio adulto",
    admittedAt: "2026-11-19T18:10:00-03:00",
    cutoffAt: "2026-11-20T19:30:00-03:00",
  },
  professionals: [
    { id: "prof-nurse-night", name: "Rosa Fuentes", role: "Enfermera clínica", discipline: "nursing" },
    { id: "prof-nurse-day", name: "Ana Morales", role: "Enfermera clínica", discipline: "nursing" },
    { id: "prof-med", name: "Tomás Ibarra", role: "Médico residente", discipline: "medicine" },
    { id: "prof-kine", name: "Camila Rojas", role: "Kinesióloga", discipline: "kinesiology" },
  ],
  shifts: [
    {
      id: "shift-night-19",
      label: "Noche 19/11",
      startsAt: "2026-11-19T20:00:00-03:00",
      endsAt: "2026-11-20T08:00:00-03:00",
    },
    {
      id: "shift-day-20",
      label: "Día 20/11",
      startsAt: "2026-11-20T08:00:00-03:00",
      endsAt: "2026-11-20T20:00:00-03:00",
    },
    {
      id: "shift-night-20",
      label: "Noche 20/11",
      startsAt: "2026-11-20T20:00:00-03:00",
      endsAt: "2026-11-21T08:00:00-03:00",
    },
  ],
  encounters: [
    {
      id: "enc-nurse-night-1",
      episodeId: DEMO_EPISODE_ID,
      authorId: "prof-nurse-night",
      shiftId: "shift-night-19",
      occurredAt: "2026-11-20T02:30:00-03:00",
      source: { type: "audio_dictation", label: "Dictado ficticio #1" },
      entries: [
        {
          id: "ent-nn1-vitals",
          kind: "vitals",
          status: "validated",
          text: "Controles nocturnos con O2 por naricera a 2 L/min.",
          measurements: [
            { code: "spo2", label: "SpO2", value: "92", unit: "%" },
            { code: "rr", label: "FR", value: "24", unit: "rpm" },
            { code: "hr", label: "FC", value: "98", unit: "lpm" },
          ],
        },
        {
          id: "ent-nn1-assessment",
          kind: "assessment",
          status: "validated",
          text: "Disnea leve al decúbito; tos productiva. Duerme a intervalos.",
        },
        {
          id: "ent-nn1-plan",
          kind: "plan",
          status: "validated",
          text: "Mantener cabecera a 30°, controles cada 4 h.",
        },
      ],
    },
    {
      id: "enc-med-day-1",
      episodeId: DEMO_EPISODE_ID,
      authorId: "prof-med",
      shiftId: "shift-day-20",
      occurredAt: "2026-11-20T09:15:00-03:00",
      source: { type: "audio_dictation", label: "Dictado ficticio #2" },
      entries: [
        {
          id: "ent-md1-assessment",
          kind: "assessment",
          status: "validated",
          text: "Neumonía adquirida en la comunidad, día 2 de tratamiento. Evolución clínica favorable, afebril.",
        },
        {
          id: "ent-md1-plan",
          kind: "plan",
          status: "validated",
          text: "Mantener ceftriaxona 2 g/día. Gases arteriales de control esta tarde. Destete de O2 según tolerancia.",
        },
        {
          id: "ent-md1-draft",
          kind: "plan",
          status: "draft",
          text: "Evaluar traslado a sala básica mañana (sin validar).",
        },
      ],
    },
    {
      id: "enc-kine-day-1",
      episodeId: DEMO_EPISODE_ID,
      authorId: "prof-kine",
      shiftId: "shift-day-20",
      occurredAt: "2026-11-20T11:00:00-03:00",
      source: { type: "audio_dictation", label: "Dictado ficticio #3" },
      entries: [
        {
          id: "ent-kd1-intervention",
          kind: "intervention",
          status: "validated",
          text: "Kinesioterapia respiratoria: técnicas de permeabilización y ejercicios de expansión. Tolera bien.",
        },
        {
          id: "ent-kd1-vitals",
          kind: "vitals",
          status: "validated",
          text: "Post sesión, con O2 a 1 L/min.",
          measurements: [{ code: "spo2", label: "SpO2", value: "94", unit: "%" }],
        },
        {
          id: "ent-kd1-plan",
          kind: "plan",
          status: "validated",
          text: "Dos sesiones diarias; sedestación al borde de cama por la tarde.",
        },
      ],
    },
    {
      id: "enc-nurse-day-1",
      episodeId: DEMO_EPISODE_ID,
      authorId: "prof-nurse-day",
      shiftId: "shift-day-20",
      occurredAt: "2026-11-20T16:40:00-03:00",
      source: { type: "audio_dictation", label: "Dictado ficticio #4" },
      entries: [
        {
          id: "ent-nd1-vitals",
          kind: "vitals",
          status: "validated",
          text: "Controles de la tarde, O2 suspendido a las 15:00.",
          measurements: [
            { code: "spo2", label: "SpO2", value: "95", unit: "%" },
            { code: "hr", label: "FC", value: "88", unit: "lpm" },
            { code: "temp", label: "Temperatura", value: "37,2", unit: "°C" },
          ],
        },
        {
          id: "ent-nd1-assessment",
          kind: "assessment",
          status: "validated",
          text: "Tolera suspensión de O2. Refiere que se retiró a las 16:00. Sedestación lograda con ayuda de kinesiología.",
        },
        {
          id: "ent-nd1-plan",
          kind: "plan",
          status: "validated",
          text: "Controles cada 6 h. Vigilar SpO2 nocturna sin O2.",
        },
      ],
    },
    {
      // Posterior al corte: no debe aparecer en el registro ni en traspasos.
      id: "enc-nurse-night-2",
      episodeId: DEMO_EPISODE_ID,
      authorId: "prof-nurse-night",
      shiftId: "shift-night-20",
      occurredAt: "2026-11-20T21:10:00-03:00",
      source: { type: "audio_dictation", label: "Dictado ficticio #5" },
      entries: [
        {
          id: "ent-nn2-vitals",
          kind: "vitals",
          status: "validated",
          text: "Ingreso de turno.",
          measurements: [{ code: "spo2", label: "SpO2", value: "90", unit: "%" }],
        },
      ],
    },
  ],
  pendings: [
    {
      id: "pend-abg",
      episodeId: DEMO_EPISODE_ID,
      title: "Tomar gases arteriales de control",
      status: "open",
      ownerId: "prof-nurse-day",
      dueAt: "2026-11-20T22:00:00-03:00",
      sourceEncounterId: "enc-med-day-1",
    },
    {
      id: "pend-kine-am",
      episodeId: DEMO_EPISODE_ID,
      title: "Reevaluar kinesioterapia respiratoria AM",
      status: "open",
      ownerId: "prof-kine",
      dueAt: "2026-11-21T10:00:00-03:00",
      sourceEncounterId: "enc-kine-day-1",
    },
    {
      id: "pend-iv-line",
      episodeId: DEMO_EPISODE_ID,
      title: "Curación de vía venosa periférica",
      status: "done",
      ownerId: "prof-nurse-night",
      dueAt: null,
      sourceEncounterId: "enc-nurse-night-1",
      closedAt: "2026-11-20T06:00:00-03:00",
      closedById: "prof-nurse-night",
    },
  ],
  openConflicts: [
    {
      id: "conflict-o2-time",
      description: "Hora de suspensión de O2 por confirmar. El control indica las 15:00 y el paciente refiere las 16:00.",
      sourceEncounterIds: ["enc-nurse-day-1"],
    },
  ],
};

export const DEMO_EPISODES: EpisodeRecord[] = [
  DEMO_EPISODE,
  {
    episode: {
      ...DEMO_EPISODE.episode,
      id: DEMO_SECOND_EPISODE_ID,
      label: "Paciente ficticio DEMO-002 · Cama 8",
    },
    professionals: DEMO_EPISODE.professionals,
    shifts: DEMO_EPISODE.shifts,
    encounters: [
      {
        id: "enc-demo-002-nurse",
        episodeId: DEMO_SECOND_EPISODE_ID,
        authorId: "prof-nurse-day",
        shiftId: "shift-day-20",
        occurredAt: "2026-11-20T14:15:00-03:00",
        source: { type: "audio_dictation", label: "Dictado ficticio · Cama 8" },
        entries: [
          {
            id: "ent-demo-002-assessment",
            kind: "assessment",
            status: "validated",
            text: "Paciente despierto. Tolera la movilización con asistencia.",
          },
          {
            id: "ent-demo-002-plan",
            kind: "plan",
            status: "validated",
            text: "Coordinar próxima movilización con kinesiología.",
          },
        ],
      },
    ],
    pendings: [
      {
        id: "pend-demo-002-movement",
        episodeId: DEMO_SECOND_EPISODE_ID,
        title: "Coordinar la próxima movilización",
        status: "open",
        ownerId: "prof-kine",
        dueAt: null,
        sourceEncounterId: "enc-demo-002-nurse",
      },
    ],
    openConflicts: [],
  },
  {
    episode: {
      ...DEMO_EPISODE.episode,
      id: DEMO_OTHER_EPISODE_ID,
      label: "Paciente ficticio DEMO-003 · Cama 3",
    },
    professionals: DEMO_EPISODE.professionals,
    shifts: DEMO_EPISODE.shifts,
    encounters: [
      {
        id: "enc-demo-003-nurse",
        episodeId: DEMO_OTHER_EPISODE_ID,
        authorId: "prof-nurse-night",
        shiftId: "shift-night-19",
        occurredAt: "2026-11-20T07:40:00-03:00",
        source: { type: "audio_dictation", label: "Dictado ficticio · Cama 3" },
        entries: [
          {
            id: "ent-demo-003-assessment",
            kind: "assessment",
            status: "validated",
            text: "Paciente refiere haber dormido bien durante el turno.",
          },
        ],
      },
    ],
    pendings: [],
    openConflicts: [],
  },
];
