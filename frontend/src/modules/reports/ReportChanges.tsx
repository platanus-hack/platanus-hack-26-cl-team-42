import { useState, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Box, Button, Callout, Flex, Grid, Link as ThemeLink, Skeleton, Text } from "@radix-ui/themes";
import { CollapsibleSection } from "../../components/CollapsibleSection";
import { sectionLabel } from "../templates/recordFields";
import { reportTitle } from "./format";
import { useReportDiff, type RecordChange, type Report, type ReportDiff } from "./api";
import { diffRows, type DiffLine, type DiffRow } from "./diffRows";

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short" });

/**
 * Qué cambió respecto del informe guardado anterior de la misma profesión, lado a lado, y qué pasó
 * con cada cambio en el registro oficial del paciente. En un borrador, el impacto es una previsión.
 */
export function ReportChangesSection({ report, enabled }: { report: Report; enabled: boolean }) {
  const { data: diff, isPending, isError } = useReportDiff(report, enabled);
  if (!enabled || isError) return null;
  if (isPending || !diff) return <Skeleton height="48px" />;

  const rows = diffRows(diff.changes);
  const conflicts = rows.filter((row) => row.lines.some((line) => line.impact === "conflict")).length;
  const title = diff.previous ? "Cambios desde el informe anterior" : "Primer informe de esta profesión";
  return (
    <CollapsibleSection
      title={title}
      detail={rows.length === 1 ? "1 cambio" : `${rows.length} cambios`}
      badge={
        conflicts > 0
          ? { label: diff.preview ? `${conflicts} chocarían` : `${conflicts} en conflicto`, color: "red" }
          : diff.preview
            ? { label: "Previsión", color: "indigo" }
            : undefined
      }
    >
      <Flex direction="column" gap="3">
        <Text size="2" color="gray">
          {diff.previous ? (
            <>
              Comparado con el{" "}
              <PreviousReportLink report={report} previous={diff.previous}>
                {reportTitle(diff.previous.sequence, report.profession).toLowerCase()}
              </PreviousReportLink>{" "}
              · {diff.previous.authorName} · {DATE_FORMAT.format(new Date(diff.previous.recordedAt))}.
            </>
          ) : (
            "No hay un informe anterior de esta profesión: todo lo que contiene es nuevo."
          )}{" "}
          {diff.preview
            ? "Es un borrador: lo nuevo se sumará al registro oficial al guardarlo, salvo lo que se indica."
            : "Lo nuevo ya está en el registro oficial, salvo lo que se indica."}
        </Text>
        {diff.preview && conflicts > 0 && (
          <Callout.Root color="red" size="1">
            <Callout.Text>Al guardarlo, lo marcado abrirá una reconciliación con el registro oficial.</Callout.Text>
          </Callout.Root>
        )}
        {rows.length === 0 ? (
          <Text size="2" color="gray">
            Sin cambios respecto del informe anterior.
          </Text>
        ) : (
          <SideBySide
            rows={rows}
            beforeLabel={diff.previous ? "Informe anterior" : "Antes"}
            afterLabel="Este informe"
            missingLabel="No mencionado"
            preview={diff.preview}
          />
        )}
        {rows.some((row) => row.kind === "removed") && (
          <Text size="1" color="gray">
            «No mencionado» no significa suspendido: este informe no lo menciona.
          </Text>
        )}
      </Flex>
    </CollapsibleSection>
  );
}

function PreviousReportLink({ report, previous, children }: { report: Report; previous: ReportDiff["previous"]; children: string }) {
  if (!report.patient || !previous) return <>{children}</>;
  return (
    <ThemeLink asChild>
      <Link to="/" search={{ patient: String(report.patient.id), report: previous.id }}>
        {children}
      </Link>
    </ThemeLink>
  );
}

interface SideBySideProps {
  rows: DiffRow[];
  beforeLabel: string;
  afterLabel: string;
  /** Qué se muestra cuando el elemento ya no está: «No mencionado» (informe) o «Retirado» (versión). */
  missingLabel: string;
  preview?: boolean;
}

/** Antes | Después, por sección. En pantallas angostas se apila como un diff línea a línea (− / +). */
export function SideBySide({ rows, beforeLabel, afterLabel, missingLabel, preview = false }: SideBySideProps) {
  const sections = [...new Set(rows.map((row) => row.section))];
  const compares = rows.some((row) => row.kind !== "added");
  if (!compares) {
    // Nada que comparar: no se muestra una columna «antes» vacía.
    return (
      <Flex direction="column" gap="1">
        <Text size="2" color="gray">
          Solo hay información nueva: ningún valor anterior cambió ni dejó de estar.
        </Text>
        <Grid columns="1" gapY="1">
          {sections.map((section) => (
            <SectionRows key={section} section={section} rows={rows} missingLabel={missingLabel} preview={preview} wide />
          ))}
        </Grid>
      </Flex>
    );
  }
  return (
    <Grid columns={{ initial: "1", sm: "2" }} gapX="3" gapY="1">
      <Box display={{ initial: "none", sm: "block" }}>
        <ColumnLabel>{beforeLabel}</ColumnLabel>
      </Box>
      <Box display={{ initial: "none", sm: "block" }}>
        <ColumnLabel>{afterLabel}</ColumnLabel>
      </Box>
      {sections.map((section) => (
        <SectionRows
          key={section}
          section={section}
          rows={rows}
          missingLabel={missingLabel}
          preview={preview}
          // Una sección con solo información nueva usa todo el ancho.
          wide={rows.every((row) => row.section !== section || row.kind === "added")}
        />
      ))}
    </Grid>
  );
}

interface SectionRowsProps {
  section: string;
  rows: DiffRow[];
  missingLabel: string;
  preview: boolean;
  wide: boolean;
}

function SectionRows({ section, rows, missingLabel, preview, wide }: SectionRowsProps) {
  return (
    <>
      <Box style={{ gridColumn: "1 / -1" }} pt="2">
        <Text size="1" weight="bold" color="gray" style={{ textTransform: "uppercase", letterSpacing: "0.04em" }}>
          {sectionLabel(section)}
        </Text>
      </Box>
      {rows
        .filter((row) => row.section === section)
        .map((row) => (
          <DiffRowCells key={row.key} row={row} missingLabel={missingLabel} preview={preview} wide={wide} />
        ))}
    </>
  );
}

function ColumnLabel({ children }: { children: string }) {
  return (
    <Text size="1" color="gray" weight="medium">
      {children}
    </Text>
  );
}

function DiffRowCells({ row, missingLabel, preview, wide }: { row: DiffRow; missingLabel: string; preview: boolean; wide: boolean }) {
  const [line] = row.lines;
  if (row.kind === "added") {
    return (
      <>
        {!wide && <Cell tone="empty" />}
        <Cell tone="added" testId={`after-${row.key}`} wide={wide}>
          <Fields title={row.title} lines={row.lines} side="after" preview={preview} />
        </Cell>
      </>
    );
  }
  if (row.kind === "removed") {
    return (
      <>
        <Cell tone="removed" testId={`before-${row.key}`}>
          <Text size="2">{line.before}</Text>
        </Cell>
        <Cell tone="missing" testId={`after-${row.key}`}>
          <Text size="2" color="gray" style={{ fontStyle: "italic" }}>
            {missingLabel}
          </Text>
          <Impact line={line} preview={preview} />
        </Cell>
      </>
    );
  }
  const hasBefore = row.lines.some((item) => item.before);
  return (
    <>
      <Cell tone={hasBefore ? "removed" : "empty"} testId={`before-${row.key}`}>
        {hasBefore && <Fields title={row.title} lines={row.lines} side="before" />}
      </Cell>
      <Cell tone="added" testId={`after-${row.key}`}>
        <Fields title={row.title} lines={row.lines} side="after" preview={preview} />
      </Cell>
    </>
  );
}

/** Los datos de un elemento en uno de los lados: «dosis: 0.3 mcg/kg/min». */
function Fields({ title, lines, side, preview = false }: { title: string; lines: DiffLine[]; side: "before" | "after"; preview?: boolean }) {
  return (
    <Flex direction="column" gap="1">
      {title && (
        <Text size="2" weight="medium">
          {title}
        </Text>
      )}
      {lines.map((line) => {
        const value = side === "before" ? line.before : line.after;
        if (side === "before" && !value) return null;
        return (
          <Flex key={line.key} direction="column">
            <Text size="2" style={{ whiteSpace: "pre-wrap" }}>
              {line.label && <Text color="gray">{line.label}: </Text>}
              {side === "after" && line.before ? <Text weight="medium">{value}</Text> : value}
            </Text>
            {side === "after" && <Impact line={line} preview={preview} />}
          </Flex>
        );
      })}
    </Flex>
  );
}

const TONES = {
  added: { background: "var(--green-a3)", border: "var(--green-a7)", sign: "+" },
  removed: { background: "var(--red-a3)", border: "var(--red-a7)", sign: "−" },
  missing: { background: "var(--gray-a2)", border: "var(--gray-a6)", sign: "" },
  empty: { background: "transparent", border: "transparent", sign: "" },
} as const;

/** Celda de la comparación; las vacías se ocultan cuando se apila en una columna. */
function Cell({ tone, testId, wide = false, children }: { tone: keyof typeof TONES; testId?: string; wide?: boolean; children?: ReactNode }) {
  const style = TONES[tone];
  return (
    <Box
      data-testid={testId}
      style={{
        gridColumn: wide ? "1 / -1" : undefined,
        background: style.background,
        borderLeft: `3px solid ${style.border}`,
        borderRadius: "var(--radius-2)",
        minWidth: 0,
      }}
      display={tone === "empty" ? { initial: "none", sm: "block" } : undefined}
      px="2"
      py="1"
    >
      <Flex gap="2" align="start">
        {style.sign && (
          <Text size="2" color="gray" aria-hidden="true" style={{ fontFamily: "var(--code-font-family)" }}>
            {style.sign}
          </Text>
        )}
        <Box style={{ minWidth: 0, flex: 1 }}>{children}</Box>
      </Flex>
    </Box>
  );
}

const IMPACT = {
  conflict: { color: "red", text: (_: string, preview: boolean) => (preview ? "Chocará con el registro oficial" : "En conflicto con el registro oficial") },
  official_differs: { color: "amber", text: (value: string, preview: boolean) => `${preview ? "El registro mantendrá" : "El registro mantiene"}: ${value}` },
  still_in_record: { color: "blue", text: () => "Sigue vigente en el registro oficial" },
  out_of_record: { color: "gray", text: () => "No quedó en el registro oficial" },
} as const;

/** Solo se anota el impacto cuando el registro oficial no quedó con lo de este informe. */
function Impact({ line, preview }: { line: DiffLine; preview: boolean }) {
  if (!line.impact || line.impact === "in_record") return null;
  const impact = IMPACT[line.impact];
  return (
    <Text size="1" color={impact.color} weight="medium">
      {impact.text(line.officialValue, preview)}
    </Text>
  );
}

/** Cambios de una versión oficial respecto de la anterior, plegados: «Ver cambios (2 nuevos · 1 cambio)». */
export function VersionChanges({ changes }: { changes: RecordChange[] }) {
  const [open, setOpen] = useState(false);
  if (changes.length === 0) return null;
  const rows = diffRows(changes);
  const count = (kind: DiffRow["kind"]) => rows.filter((row) => row.kind === kind).length;
  const summary = [
    plural(count("added"), "nuevo", "nuevos"),
    plural(count("changed"), "cambio", "cambios"),
    plural(count("removed"), "retirado", "retirados"),
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Flex direction="column" gap="2" style={{ width: "100%" }}>
      <Flex>
        <Button size="1" variant="ghost" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? "Ocultar cambios" : `Ver cambios (${summary})`}
        </Button>
      </Flex>
      {open && <SideBySide rows={rows} beforeLabel="Versión anterior" afterLabel="Esta versión" missingLabel="Retirado" />}
    </Flex>
  );
}

function plural(count: number, one: string, many: string): string {
  return count === 0 ? "" : `${count} ${count === 1 ? one : many}`;
}
