import { Badge, Flex, Text } from "@radix-ui/themes";
import { ComplementDialog } from "../templates/ComplementDialog";
import { RecordValue } from "../templates/RecordSections";
import { sectionLabel } from "../templates/recordFields";
import type { Report } from "./api";

export function sectionAnchor(key: string): string {
  return `report-section-${key}`;
}

interface SectionBlockProps {
  report: Report;
  sectionKey: string;
  /** Nombres de los campos sin información de esta sección. */
  pendingFields: string[];
  focused?: boolean;
  /** Muestra «Agregar información» (texto o audio) para completar lo que falta. */
  canComplete?: boolean;
  busy?: boolean;
}

/** Una sección del informe con su contenido, lo que le falta y, si se puede, cómo completarlo. */
export function SectionBlock({ report, sectionKey, pendingFields, focused = false, canComplete = false, busy = false }: SectionBlockProps) {
  const label = sectionLabel(sectionKey);

  return (
    <Flex
      id={sectionAnchor(sectionKey)}
      direction="column"
      gap="2"
      p="3"
      style={{
        scrollMarginTop: 80,
        borderRadius: "var(--radius-3)",
        background: "var(--gray-a2)",
        outline: focused ? "2px solid var(--indigo-9)" : undefined,
      }}
    >
      <Flex justify="between" align="center" gap="2" wrap="wrap">
        <Flex align="center" gap="2" wrap="wrap">
          <Text weight="medium">{label}</Text>
          {focused && (
            <Badge color="indigo" variant="soft">
              Referenciada
            </Badge>
          )}
          {pendingFields.length > 0 && (
            <Badge color="amber" variant="soft">
              {pendingFields.length} {pendingFields.length === 1 ? "campo pendiente" : "campos pendientes"}
            </Badge>
          )}
        </Flex>
        {canComplete && pendingFields.length > 0 && (
          <ComplementDialog extractionId={report.extractionId} section={sectionKey} label={label} disabled={busy} />
        )}
      </Flex>
      {pendingFields.length > 0 && (
        <Text size="1" color="gray">
          Sin información: {pendingFields.slice(0, 6).join(", ")}
          {pendingFields.length > 6 && ` y ${pendingFields.length - 6} más`}
        </Text>
      )}
      <RecordValue value={(report.data ?? {})[sectionKey]} />
    </Flex>
  );
}
