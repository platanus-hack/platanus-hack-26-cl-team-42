import { useEffect, useMemo } from "react";
import { Badge, Button, Card, Flex, Grid, Heading, Select, Spinner, Text, TextArea } from "@radix-ui/themes";
import { Link, useNavigate } from "@tanstack/react-router";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { useEpisodeRecord } from "../episode/api";
import { CopyButton, DemoEpisodeBanner, OpenConflicts, PendingStatusBadge, SourceLink } from "../episode/components";
import { DEMO_EPISODE_ID } from "../episode/fixture";
import { formatClinicalTime } from "../episode/format";
import type { Encounter, EpisodeRecord, RecordFilter } from "../episode/model";
import {
  authorLine,
  datumText,
  describeFilter,
  encounterAnchor,
  ENTRY_KIND_LABEL,
  renderRecordText,
  selectRecord,
  type RecordView,
} from "../episode/record";
import type { ClinicalRecordSearch } from "../../routes/_authenticated/official-form";

const ALL = "all";

export function ClinicalRecordPage({ search }: { search: ClinicalRecordSearch }) {
  const { data: record, isPending, error } = useEpisodeRecord(DEMO_EPISODE_ID);

  return (
    <ModulePage stepId="official-form" connected>
      {isPending ? (
        <Flex justify="center" py="6">
          <Spinner size="3" />
        </Flex>
      ) : !record ? (
        <EmptyState title="Sin episodio" description={error?.message ?? "No se pudo cargar el episodio de demostración."} />
      ) : (
        <ClinicalRecord record={record} search={search} />
      )}
    </ModulePage>
  );
}

function ClinicalRecord({ record, search }: { record: EpisodeRecord; search: ClinicalRecordSearch }) {
  const filter: RecordFilter = { professionalId: search.professional, shiftId: search.shift };
  const view = useMemo(
    () => selectRecord(record, { professionalId: search.professional, shiftId: search.shift }),
    [record, search.professional, search.shift],
  );
  const text = useMemo(() => renderRecordText(record, view), [record, view]);

  useEffect(() => {
    if (!search.encounter) return;
    document.getElementById(encounterAnchor(search.encounter))?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [search.encounter, view]);

  return (
    <Flex direction="column" gap="4">
      <DemoEpisodeBanner episode={record.episode}>
        <Button size="2" asChild>
          <Link to="/handoff" search={{ as: filter.professionalId, tab: "send" }}>
            Traspasar este episodio
          </Link>
        </Button>
      </DemoEpisodeBanner>

      <RecordFilters record={record} search={search} />

      <Grid columns={{ initial: "1", md: "3fr 2fr" }} gap="4" align="start">
        <Flex direction="column" gap="3">
          <Heading size="4">Atenciones ({view.encounters.length})</Heading>
          {view.encounters.length === 0 ? (
            <EmptyState
              title="Sin atenciones"
              description="No hay atenciones validadas antes del corte para este filtro."
            />
          ) : (
            view.encounters.map((encounter) => (
              <EncounterCard
                key={encounter.id}
                record={record}
                encounter={encounter}
                highlighted={encounter.id === search.encounter}
              />
            ))
          )}
        </Flex>
        <RecordSidebar record={record} view={view} />
      </Grid>

      <Card size="3">
        <Flex direction="column" gap="3">
          <Flex align="center" justify="between" gap="3" wrap="wrap">
            <Flex direction="column">
              <Heading size="4">Vista previa para la ficha institucional</Heading>
              <Text size="2" color="gray">
                Texto plano de {describeFilter(record, filter)}.
              </Text>
            </Flex>
            <CopyButton text={text} />
          </Flex>
          <TextArea readOnly value={text} rows={16} aria-label="Texto para la ficha institucional" style={{ fontFamily: "var(--code-font-family)" }} />
        </Flex>
      </Card>
    </Flex>
  );
}

function RecordFilters({ record, search }: { record: EpisodeRecord; search: ClinicalRecordSearch }) {
  const navigate = useNavigate();
  const update = (patch: Partial<ClinicalRecordSearch>) =>
    navigate({ to: "/official-form", search: { ...search, ...patch, encounter: undefined } });

  return (
    <Flex gap="4" wrap="wrap" align="end">
      <Flex direction="column" gap="1">
        <Text size="2" weight="medium">
          Profesional
        </Text>
        <Select.Root
          value={search.professional ?? ALL}
          onValueChange={(value) => update({ professional: value === ALL ? undefined : value })}
        >
          <Select.Trigger aria-label="Filtrar por profesional" style={{ minWidth: 240 }} />
          <Select.Content>
            <Select.Item value={ALL}>Todos los profesionales</Select.Item>
            {record.professionals.map((professional) => (
              <Select.Item key={professional.id} value={professional.id}>
                {professional.name} · {professional.role}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </Flex>
      <Flex direction="column" gap="1">
        <Text size="2" weight="medium">
          Turno
        </Text>
        <Select.Root
          value={search.shift ?? ALL}
          onValueChange={(value) => update({ shift: value === ALL ? undefined : value })}
        >
          <Select.Trigger aria-label="Filtrar por turno" style={{ minWidth: 180 }} />
          <Select.Content>
            <Select.Item value={ALL}>Todos los turnos</Select.Item>
            {record.shifts.map((shift) => (
              <Select.Item key={shift.id} value={shift.id}>
                {shift.label}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </Flex>
      {(search.professional || search.shift) && (
        <Button variant="ghost" color="gray" onClick={() => update({ professional: undefined, shift: undefined })}>
          Quitar filtros
        </Button>
      )}
    </Flex>
  );
}

function EncounterCard({
  record,
  encounter,
  highlighted,
}: {
  record: EpisodeRecord;
  encounter: Encounter;
  highlighted: boolean;
}) {
  const shift = record.shifts.find((item) => item.id === encounter.shiftId);
  return (
    <Card
      id={encounterAnchor(encounter.id)}
      style={highlighted ? { outline: "2px solid var(--accent-9)", outlineOffset: 2 } : undefined}
    >
      <Flex direction="column" gap="3">
        <Flex align="center" justify="between" gap="2" wrap="wrap">
          <Text weight="bold">{authorLine(record, encounter.authorId)}</Text>
          <Flex gap="2" align="center">
            {highlighted && (
              <Badge color="teal" variant="solid">
                Atención de origen
              </Badge>
            )}
            <Badge color="gray" variant="soft">
              {formatClinicalTime(encounter.occurredAt)}
              {shift ? ` · ${shift.label}` : ""}
            </Badge>
          </Flex>
        </Flex>
        <Text size="1" color="gray">
          {encounter.source.label} · atención {encounter.id}
        </Text>
        {encounter.entries.map((entry) => (
          <Flex key={entry.id} direction="column" gap="1">
            <Flex gap="2" align="center">
              <Badge variant="surface">{ENTRY_KIND_LABEL[entry.kind]}</Badge>
              <Badge color="green" variant="soft">
                Validada
              </Badge>
            </Flex>
            <Text size="2">{entry.text}</Text>
            {entry.measurements && entry.measurements.length > 0 && (
              <Flex gap="2" wrap="wrap">
                {entry.measurements.map((m) => (
                  <Badge key={m.code} color="blue" variant="soft">
                    {m.label} {m.value} {m.unit}
                  </Badge>
                ))}
              </Flex>
            )}
          </Flex>
        ))}
      </Flex>
    </Card>
  );
}

function RecordSidebar({ record, view }: { record: EpisodeRecord; view: RecordView }) {
  return (
    <Flex direction="column" gap="3">
      <OpenConflicts conflicts={view.openConflicts} />
      <Card>
        <Flex direction="column" gap="2">
          <Heading size="3">Datos al corte</Heading>
          {view.cutoffData.length === 0 && (
            <Text size="2" color="gray">
              Sin mediciones para este filtro.
            </Text>
          )}
          {view.cutoffData.map((datum) => (
            <Flex key={datum.code} direction="column">
              <Text size="2" weight="medium">
                {datumText(datum)}
              </Text>
              <Text size="1" color="gray">
                {formatClinicalTime(datum.observedAt)} · {authorLine(record, datum.source.authorId)} ·{" "}
                <SourceLink encounterId={datum.source.encounterId}>ver origen</SourceLink>
              </Text>
            </Flex>
          ))}
        </Flex>
      </Card>
      <Card>
        <Flex direction="column" gap="2">
          <Heading size="3">Plan vigente validado</Heading>
          {view.plan.length === 0 && (
            <Text size="2" color="gray">
              Sin plan validado para este filtro.
            </Text>
          )}
          {view.plan.map((item) => (
            <Flex key={item.entryId} direction="column">
              <Text size="2">{item.text}</Text>
              <Text size="1" color="gray">
                {authorLine(record, item.authorId)} · {formatClinicalTime(item.occurredAt)} ·{" "}
                <SourceLink encounterId={item.encounterId}>ver origen</SourceLink>
              </Text>
            </Flex>
          ))}
        </Flex>
      </Card>
      <Card>
        <Flex direction="column" gap="2">
          <Heading size="3">Pendientes</Heading>
          {view.pendings.length === 0 && (
            <Text size="2" color="gray">
              Sin pendientes para este filtro.
            </Text>
          )}
          {view.pendings.map((pending) => (
            <Flex key={pending.id} direction="column">
              <Flex gap="2" align="center">
                <PendingStatusBadge status={pending.status} />
                <Text size="2">{pending.title}</Text>
              </Flex>
              <Text size="1" color="gray">
                {authorLine(record, pending.ownerId)}
                {pending.dueAt ? ` · plazo ${formatClinicalTime(pending.dueAt)}` : ""} ·{" "}
                <SourceLink encounterId={pending.sourceEncounterId}>ver origen</SourceLink>
              </Text>
            </Flex>
          ))}
        </Flex>
      </Card>
    </Flex>
  );
}
