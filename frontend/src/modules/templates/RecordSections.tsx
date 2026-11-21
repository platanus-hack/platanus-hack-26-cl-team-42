import { Badge, Callout, Card, Flex, Heading, Progress, Skeleton, Spinner, Text } from "@radix-ui/themes";
import { ComplementDialog } from "./ComplementDialog";
import { isExtractionInProgress, type Extraction, type TemplateDetail } from "./api";
import { countFields, isEmptyValue, sectionLabel, sectionState, type SectionState } from "./recordFields";

interface RecordViewProps {
  extraction: Extraction;
  template: TemplateDetail | undefined;
}

/** La plantilla completa: cada sección con lo extraído hasta ahora y lo que sigue pendiente. */
export function RecordView({ extraction, template }: RecordViewProps) {
  const inProgress = isExtractionInProgress(extraction);
  const data = extraction.data ?? {};
  const sections = template?.output_schema.required ?? Object.keys(data);
  const states = sections.map((key) => sectionState(key in data, data[key], inProgress));
  const withInformation = states.filter((state) => state === "partial" || state === "complete").length;
  const incomplete = states.filter((state) => state === "pending" || state === "partial").length;

  return (
    <Flex direction="column" gap="3">
      <Flex direction="column" gap="2">
        <Flex align="center" gap="2">
          {inProgress && <Spinner size="2" />}
          <Heading size="3">{extraction.templateName}</Heading>
        </Flex>
        <Progress value={withInformation} max={Math.max(sections.length, 1)} />
        <Text size="2" color="gray">
          {inProgress
            ? `Llenando la plantilla… ${withInformation} de ${sections.length} secciones con información`
            : `${withInformation} de ${sections.length} secciones con información · ${incomplete} con información pendiente`}
        </Text>
      </Flex>

      {extraction.error && !inProgress && (
        <Callout.Root color="amber" size="1">
          <Callout.Text>{extraction.error}</Callout.Text>
        </Callout.Root>
      )}

      {sections.map((key, index) => (
        <SectionCard
          key={key}
          extractionId={extraction.id}
          sectionKey={key}
          description={template?.output_schema.properties[key]?.description}
          value={data[key]}
          state={states[index]}
          busy={inProgress}
        />
      ))}
    </Flex>
  );
}

interface SectionCardProps {
  extractionId: string;
  sectionKey: string;
  description: string | undefined;
  value: unknown;
  state: SectionState;
  busy: boolean;
}

function SectionCard({ extractionId, sectionKey, description, value, state, busy }: SectionCardProps) {
  const label = sectionLabel(sectionKey);
  const hasBody = state === "partial" || state === "complete";

  return (
    <Card variant="surface">
      <Flex direction="column" gap="2">
        <Flex justify="between" align="center" gap="3" wrap="wrap">
          <Flex direction="column" style={{ minWidth: 0 }}>
            <Text weight="medium">{label}</Text>
            {description && (
              <Text size="1" color="gray">
                {description}
              </Text>
            )}
          </Flex>
          <Flex align="center" gap="2">
            <StateBadge state={state} pending={countFields(value).pending} />
            {(state === "pending" || state === "partial") && (
              <ComplementDialog extractionId={extractionId} section={sectionKey} label={label} disabled={busy} />
            )}
          </Flex>
        </Flex>

        {state === "waiting" && (
          <Skeleton>
            <Text size="2">Esperando información de esta sección…</Text>
          </Skeleton>
        )}
        {hasBody && <RecordValue value={value} />}
      </Flex>
    </Card>
  );
}

function StateBadge({ state, pending }: { state: SectionState; pending: number }) {
  switch (state) {
    case "waiting":
      return (
        <Badge color="gray" variant="soft">
          Esperando…
        </Badge>
      );
    case "pending":
      return (
        <Badge color="amber" variant="soft">
          Información pendiente
        </Badge>
      );
    case "partial":
      return (
        <Badge color="amber" variant="soft">
          {pending} {pending === 1 ? "campo pendiente" : "campos pendientes"}
        </Badge>
      );
    case "complete":
      return (
        <Badge color="green" variant="soft">
          Completo
        </Badge>
      );
  }
}

function PendingChip() {
  return (
    <Badge color="amber" variant="outline" size="1">
      Pendiente
    </Badge>
  );
}

function RecordValue({ value }: { value: unknown }) {
  if (isEmptyValue(value)) return <PendingChip />;
  if (Array.isArray(value)) {
    return (
      <Flex direction="column" gap="2">
        {value.map((item, index) => (
          <Card key={index} variant="classic">
            <RecordValue value={item} />
          </Card>
        ))}
      </Flex>
    );
  }
  if (typeof value === "object") {
    return (
      <Flex direction="column" gap="1">
        {Object.entries(value as Record<string, unknown>).map(([key, child]) => {
          const nested = !isEmptyValue(child) && typeof child === "object";
          return (
            <Flex key={key} direction={nested ? "column" : "row"} gap={nested ? "1" : "2"} align={nested ? "start" : "baseline"} wrap="wrap">
              <Text size="2" color="gray">
                {sectionLabel(key)}:
              </Text>
              {nested ? (
                <Flex pl="3" style={{ width: "100%" }}>
                  <RecordValue value={child} />
                </Flex>
              ) : (
                <RecordValue value={child} />
              )}
            </Flex>
          );
        })}
      </Flex>
    );
  }
  return <Text size="2">{String(value)}</Text>;
}
