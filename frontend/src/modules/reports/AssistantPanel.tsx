import { Fragment, useEffect, useState, type ReactNode } from "react";
import { Button, Callout, Flex, Heading, IconButton, Spinner, Text, TextField } from "@radix-ui/themes";
import { Link, useSearch } from "@tanstack/react-router";
import { usePatients } from "../patients/api";
import { professionLabel } from "../recordings/professions";
import { sectionLabel } from "../templates/recordFields";
import { reportTitle } from "./format";
import { useAskReports, type AssistantAnswer } from "./api";

interface Exchange {
  question: string;
  answer: AssistantAnswer;
}

/** Botón flotante + panel lateral: sigue abierto mientras se graba, se navega o se revisan informes. */
export function AssistantDrawer() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<Exchange[]>([]);
  const ask = useAskReports();
  const { data: patients = [] } = usePatients();
  const { patient } = useSearch({ strict: false }) as { patient?: string };
  const current = patient ? patients.find((item) => String(item.id) === patient) : undefined;
  const patientId = current?.id;
  const visible = open;

  // Empuja la página (en pantallas anchas) en vez de taparla.
  useEffect(() => {
    if (visible) document.documentElement.dataset.assistant = "open";
    else delete document.documentElement.dataset.assistant;
    return () => {
      delete document.documentElement.dataset.assistant;
    };
  }, [visible]);

  // La conversación pertenece al paciente seleccionado: al cambiar de paciente empieza de cero.
  useEffect(() => {
    setHistory([]);
    setQuestion("");
    ask.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  const submit = () => {
    const text = question.trim();
    if (!text || ask.isPending || patientId === undefined) return;
    ask.mutate(
      { question: text, patientId },
      {
        onSuccess: (answer) => {
          setHistory((items) => [{ question: text, answer }, ...items]);
          setQuestion("");
        },
      },
    );
  };

  return (
    <>
      {!open && (
        <button type="button" className="assistant-fab" onClick={() => setOpen(true)} aria-label="Abrir asistente">
          <span aria-hidden>✦</span>
          <span className="assistant-fab__label">Preguntar</span>
        </button>
      )}
      <aside className="assistant-drawer" data-open={visible} aria-hidden={!visible} aria-label="Pregúntale a los informes">
        <Flex align="center" gap="3" p="3" className="assistant-drawer__head">
          <Flex className="assistant-drawer__mark" align="center" justify="center" aria-hidden>
            ✦
          </Flex>
          <Flex direction="column" style={{ flex: 1 }}>
            <Heading size="3">Pregúntale a los informes</Heading>
            <Text size="1" color="gray">
              Solo este paciente · cada dato trae su referencia.
            </Text>
          </Flex>
          <IconButton variant="ghost" color="gray" aria-label="Cerrar asistente" onClick={() => setOpen(false)}>
            ✕
          </IconButton>
        </Flex>

        <Flex direction="column" gap="3" p="3" className="assistant-drawer__body">
          {current ? (
            <Text size="2" weight="medium">
              {current.name}
            </Text>
          ) : (
            <Text size="2" color="gray">
              Abre un paciente en «Mis pacientes» para consultar sus informes. El asistente responde solo sobre el
              paciente seleccionado.
            </Text>
          )}
          {ask.isError && (
            <Callout.Root color="red" size="1">
              <Callout.Text>{ask.error.message}</Callout.Text>
            </Callout.Root>
          )}
          {history.length === 0 && !ask.isPending && (
            <Text size="2" color="gray">
              Ej.: ¿Qué drogas vasoactivas usa y en qué dosis?
            </Text>
          )}
          {ask.isPending && (
            <Flex align="center" gap="2">
              <Spinner size="2" />
              <Text size="2" color="gray">
                Revisando los informes…
              </Text>
            </Flex>
          )}
          {history.map((exchange, index) => (
            <Answer key={`${exchange.question}-${index}`} exchange={exchange} />
          ))}
        </Flex>

        <Flex gap="2" p="3" className="assistant-drawer__foot">
          <TextField.Root
            style={{ flex: 1 }}
            disabled={!current}
            placeholder={current ? "Escribe tu pregunta" : "Selecciona un paciente"}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submit();
            }}
          />
          <Button loading={ask.isPending} disabled={!current || !question.trim()} onClick={submit}>
            Preguntar
          </Button>
        </Flex>
      </aside>
    </>
  );
}

function Answer({ exchange }: { exchange: Exchange }) {
  const { answer, references } = exchange.answer;
  return (
    <Flex direction="column" gap="3">
      <Flex justify="end">
        <Text
          size="2"
          weight="medium"
          style={{
            background: "var(--indigo-9)",
            color: "white",
            padding: "8px 12px",
            borderRadius: "var(--radius-3)",
            maxWidth: "85%",
          }}
        >
          {exchange.question}
        </Text>
      </Flex>
      <Flex
        direction="column"
        gap="2"
        p="3"
        style={{
          background: "var(--gray-a2)",
          borderLeft: "3px solid var(--violet-9)",
          borderRadius: "var(--radius-3)",
        }}
      >
        <FormattedAnswer text={answer} />
      <References references={references} />
      </Flex>
    </Flex>
  );
}

/** Las referencias de la respuesta, colapsadas: se abren solo si se quiere verificar un dato. */
function References({ references }: { references: AssistantAnswer["references"] }) {
  const [open, setOpen] = useState(false);
  if (references.length === 0) return null;
  return (
    <Flex direction="column" gap="1">
      <Flex>
        <Button size="1" variant="ghost" color="gray" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? "▾" : "▸"} Referencias ({references.length})
        </Button>
      </Flex>
      {open && (
        <Flex direction="column" gap="1">
            {references.map((reference) => (
              <Text key={`${reference.reportId ?? "e"}-${reference.section ?? reference.evidenceId}`} size="1">
                {reference.evidenceId ? (
                  <Link to="/" search={{ patient: reference.patientId !== null ? String(reference.patientId) : undefined }}>
                    Examen · {reference.evidenceTitle} · {reference.patientName}
                  </Link>
                ) : (
                  <Link
                    to="/"
                    search={{
                      patient: reference.patientId !== null ? String(reference.patientId) : undefined,
                      report: reference.reportId ?? undefined,
                      section: reference.section ?? undefined,
                    }}
                  >
                    {reportTitle(reference.sequence, reference.profession)} · {reference.patientName} ·{" "}
                    {sectionLabel(reference.section ?? "")}
                  </Link>
                )}
                {reference.detail && <> — «{reference.detail}»</>}
                <span style={{ color: "var(--gray-11)" }}>
                  {" "}
                  ({reference.profession ? `${professionLabel(reference.profession)}, ` : "evidencia cargada por "}
                  {reference.authorName})
                </span>
              </Text>
            ))}
        </Flex>
      )}
    </Flex>
  );
}

/** Respuesta con secciones («## Título»), viñetas («- ») y **negritas**. */
function FormattedAnswer({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (bullets.length === 0) return;
    const items = bullets;
    bullets = [];
    blocks.push(
      <Flex key={`ul-${blocks.length}`} asChild direction="column" gap="1">
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          {items.map((item, index) => (
            <li key={index}>
              <Text size="2">{inline(item)}</Text>
            </li>
          ))}
        </ul>
      </Flex>,
    );
  };

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const heading = /^#{1,6}\s+(.*)$/.exec(line);
    const bullet = /^[-*•]\s+(.*)$/.exec(line);
    if (bullet) {
      bullets.push(bullet[1]);
      continue;
    }
    flush();
    if (heading) {
      blocks.push(
        <Text
          key={`h-${blocks.length}`}
          size="1"
          weight="bold"
          color="violet"
          style={{ textTransform: "uppercase", letterSpacing: "0.04em", marginTop: 6 }}
        >
          {heading[1]}
        </Text>,
      );
    } else if (line) {
      blocks.push(
        <Text key={`p-${blocks.length}`} size="2">
          {inline(line)}
        </Text>,
      );
    }
  }
  flush();
  return <Flex direction="column" gap="2">{blocks}</Flex>;
}

function inline(text: string): ReactNode {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={index}>{part.slice(2, -2)}</strong>
    ) : (
      <Fragment key={index}>{part}</Fragment>
    ),
  );
}
