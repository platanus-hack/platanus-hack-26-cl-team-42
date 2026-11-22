import { useState } from "react";
import { Badge, Button, Callout, Card, Flex, Grid, RadioGroup, Text, TextArea, TextField } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { professionLabel } from "../recordings/professions";
import { AgentCouncil } from "../panel/AgentCouncil";
import { sectionLabel } from "../templates/recordFields";
import {
  useConflictAction,
  type Conflict,
  type ConflictNote,
  type ConflictSide,
  type Resolution,
} from "./api";

const DATE_FORMAT = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" });
const MODE_LABEL: Record<Resolution["mode"], string> = {
  accepted: "Uno aceptó el valor del otro",
  consensus: "Consenso",
  off_shift: "Decidió quien seguía en turno",
  sole: "Decidió el único participante",
};

/**
 * Un choque entre dos informes: qué se contradice, por qué y cómo resolverlo entre los dos. A la
 * derecha (o debajo, en pantallas angostas) queda la conversación con las razones de cada uno.
 */
export function ConflictCard({ conflict, patientId, reportId }: { conflict: Conflict; patientId: number; reportId: string }) {
  const resolved = conflict.status === "resolved";
  const onShift = (name: string) => conflict.participantsShift.find((participant) => participant.name === name)?.onShift;
  return (
    <Card variant="surface">
      <Grid columns={{ initial: "1", md: "minmax(0, 1fr) 240px" }} gap="4">
        <Flex direction="column" gap="3" style={{ minWidth: 0 }}>
          <Flex justify="between" align="center" gap="2" wrap="wrap">
            <Flex align="center" gap="2" wrap="wrap">
              <Text weight="medium">{conflict.label}</Text>
              {conflict.kind === "allergy" ? (
                <Badge color="red" variant="soft">
                  Riesgo de seguridad
                </Badge>
              ) : (
                <Text size="1" color="gray">
                  Dato distinto
                </Text>
              )}
            </Flex>
            <Badge color={resolved ? "green" : "amber"} variant="soft">
              {resolved ? "Resuelto" : "Por resolver"}
            </Badge>
          </Flex>

          <Grid columns={{ initial: "1", sm: "2" }} gap="3">
            <SideBox
              side={conflict.sideA}
              onShift={onShift(conflict.sideA.authorName)}
              mine={conflict.myRole === "a" || conflict.myRole === "both"}
              chosen={resolved && conflict.resolution?.side === "a"}
            />
            <SideBox
              side={conflict.sideB}
              onShift={onShift(conflict.sideB.authorName)}
              mine={conflict.myRole === "b" || conflict.myRole === "both"}
              chosen={resolved && conflict.resolution?.side === "b"}
            />
          </Grid>

          <AgentPanel conflict={conflict} />

          <AgentCouncil conflictId={conflict.id} patientId={patientId} canLaunch={conflict.myRole !== null} />

          {resolved && conflict.resolution ? <ResolutionSummary resolution={conflict.resolution} /> : <Actions conflict={conflict} />}

          <Link
            to="/"
            search={{ patient: String(patientId), report: conflict.sideB.reportId ?? reportId, section: conflict.section }}
            style={{ fontSize: "var(--font-size-1)" }}
          >
            Ver la sección «{sectionLabel(conflict.section)}» en el informe
          </Link>
        </Flex>

        <Notes conflict={conflict} />
      </Grid>
    </Card>
  );
}

function SideBox({ side, onShift, mine, chosen }: { side: ConflictSide; onShift?: boolean; mine: boolean; chosen: boolean }) {
  return (
    <Flex
      direction="column"
      gap="1"
      p="3"
      style={{
        borderRadius: "var(--radius-3)",
        background: "var(--gray-a2)",
        outline: chosen ? "2px solid var(--green-9)" : undefined,
      }}
    >
      <Flex align="center" gap="2" wrap="wrap">
        <Text size="2" weight="medium">
          {side.authorName} · {professionLabel(side.profession)}
        </Text>
        {mine && (
          <Badge variant="soft" size="1">
            Tu registro
          </Badge>
        )}
        {chosen && (
          <Badge color="green" variant="soft" size="1">
            Elegido
          </Badge>
        )}
      </Flex>
      {onShift !== undefined && (
        <Flex align="center" gap="1">
          <span
            aria-hidden="true"
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: onShift ? "var(--green-9)" : "var(--gray-8)",
            }}
          />
          <Text size="1" color="gray">
            {onShift ? "De turno" : "Fuera de turno"}
          </Text>
        </Flex>
      )}
      <Text size="4">{side.value}</Text>
      {side.evidence && (
        <Text size="1" color="gray">
          «{side.evidence}»
        </Text>
      )}
    </Flex>
  );
}

function ResolutionSummary({ resolution }: { resolution: Resolution }) {
  return (
    <Callout.Root color="green" size="1">
      <Callout.Text>
        Queda «{resolution.value}» · {MODE_LABEL[resolution.mode]} ({resolution.decidedByName},{" "}
        {DATE_FORMAT.format(new Date(resolution.decidedAt))}).
      </Callout.Text>
    </Callout.Root>
  );
}

type Side = "a" | "b";
type ChoiceBody = { side: Side } | { value: string };

/**
 * Cómo se resuelve según quién puede participar: si el otro sigue de turno, hay que llegar a
 * consenso (aceptar su valor o proponer); si no, decides tú entre las opciones.
 */
function Actions({ conflict }: { conflict: Conflict }) {
  const act = useConflictAction();

  if (conflict.myRole === null) {
    return (
      <Text size="2" color="gray">
        Esperando a los profesionales implicados.
      </Text>
    );
  }
  if (!conflict.iAmOnShift) {
    return (
      <Callout.Root color="gray" size="1">
        <Callout.Text>
          Estás fuera de turno: no participas de la resolución. Quien siga de turno puede decidir y tú verás el resultado
          aquí.
        </Callout.Text>
      </Callout.Root>
    );
  }
  const mySide: Side = conflict.myRole === "b" ? "b" : "a";
  const otherSide: Side = mySide === "a" ? "b" : "a";
  const sides = { a: conflict.sideA, b: conflict.sideB };
  const other = conflict.myRole === "both" ? null : sides[otherSide];
  const submit = (action: "decide" | "propose", body: ChoiceBody) => act.mutate({ conflictId: conflict.id, action, body });

  return (
    <Flex direction="column" gap="3">
      {conflict.proposal && (
        <Callout.Root color="gray" variant="surface" size="1">
          <Flex direction="column" gap="2">
            <Callout.Text>
              <strong>{conflict.proposal.byName}</strong> propone: {conflict.proposal.label}
            </Callout.Text>
            {conflict.canAgree && (
              <Flex>
                <Button size="1" loading={act.isPending} onClick={() => act.mutate({ conflictId: conflict.id, action: "agree" })}>
                  Estoy de acuerdo
                </Button>
              </Flex>
            )}
          </Flex>
        </Callout.Root>
      )}

      {conflict.canDecide ? (
        <ChoiceForm
          intro={
            other
              ? `${other.authorName} (${professionLabel(other.profession)}) está fuera de turno: decides tú. Quedará anotado que conocías su registro.`
              : "Eres el único participante: decides tú."
          }
          options={
            other
              ? [
                  { side: mySide, label: "Mantener mi valor", value: sides[mySide].value },
                  { side: otherSide, label: `Usar el de ${other.authorName}`, value: other.value },
                ]
              : [
                  { side: "a", label: "Usar", value: conflict.sideA.value },
                  { side: "b", label: "Usar", value: conflict.sideB.value },
                ]
          }
          allowCustom={conflict.kind === "value"}
          submitLabel="Confirmar decisión"
          pending={act.isPending}
          onSubmit={(body) => submit("decide", body)}
        />
      ) : (
        other && (
          <Flex direction="column" gap="3">
            {conflict.canAccept && (
              <Flex>
                <Button loading={act.isPending} onClick={() => act.mutate({ conflictId: conflict.id, action: "accept" })}>
                  Aceptar el de {other.authorName} · {other.value}
                </Button>
              </Flex>
            )}
            <ChoiceForm
              intro={`${other.authorName} sigue de turno: acepta su valor o propón otro para llegar a consenso.`}
              options={[{ side: mySide, label: "Mi valor", value: sides[mySide].value }]}
              allowCustom={conflict.kind === "value"}
              submitLabel="Proponer"
              submitVariant="soft"
              pending={act.isPending}
              onSubmit={(body) => submit("propose", body)}
            />
          </Flex>
        )
      )}

      {act.isError && (
        <Text size="2" color="red">
          {act.error.message}
        </Text>
      )}
    </Flex>
  );
}

interface ChoiceOption {
  side: Side;
  label: string;
  value: string;
}

/** Opciones excluyentes (los valores registrados y, si aplica, uno distinto) con un solo botón para confirmar. */
function ChoiceForm({
  intro,
  options,
  allowCustom,
  submitLabel,
  submitVariant = "solid",
  pending,
  onSubmit,
}: {
  intro: string;
  options: ChoiceOption[];
  allowCustom: boolean;
  submitLabel: string;
  submitVariant?: "solid" | "soft";
  pending: boolean;
  onSubmit: (body: ChoiceBody) => void;
}) {
  const [choice, setChoice] = useState<string>("");
  const [custom, setCustom] = useState("");
  const body: ChoiceBody | null =
    choice === "custom" ? (custom.trim() ? { value: custom.trim() } : null) : choice ? { side: choice as Side } : null;

  return (
    <Flex direction="column" gap="2">
      <Text size="1" color="gray">
        {intro}
      </Text>
      <RadioGroup.Root value={choice} onValueChange={setChoice} size="2">
        <Flex direction="column" gap="2">
          {options.map((option) => (
            <RadioGroup.Item key={option.side} value={option.side}>
              {option.label} · <strong>{option.value}</strong>
            </RadioGroup.Item>
          ))}
          {allowCustom && (
            <Flex align="center" gap="2">
              <RadioGroup.Item value="custom">Otro valor</RadioGroup.Item>
              <TextField.Root
                size="1"
                placeholder="Valor"
                value={custom}
                onChange={(event) => setCustom(event.target.value)}
                onFocus={() => setChoice("custom")}
              />
            </Flex>
          )}
        </Flex>
      </RadioGroup.Root>
      <Flex>
        <Button variant={submitVariant} disabled={!body} loading={pending} onClick={() => body && onSubmit(body)}>
          {submitLabel}
        </Button>
      </Flex>
    </Flex>
  );
}

/** Lo que dice el agente: por qué chocan los datos, su orientación (ya generada) y a quién consultar. */
function AgentPanel({ conflict }: { conflict: Conflict }) {
  const act = useConflictAction();
  const guidance = conflict.guidance;
  const candidate = guidance?.externalCandidate ?? null;
  const asked = candidate !== null && conflict.consults.some((consult) => consult.consultantName === candidate.name);
  const recommended =
    !guidance || guidance.recommendedSide === "none" ? null : guidance.recommendedSide === "a" ? conflict.sideA : conflict.sideB;
  const canAsk = conflict.status === "open" && conflict.iAmOnShift && conflict.myRole !== null;

  return (
    <Callout.Root color={conflict.kind === "allergy" ? "red" : "gray"} size="1">
      <Flex direction="column" gap="2">
        <Callout.Text>
          <strong>Agente:</strong> {conflict.explanation}
        </Callout.Text>
        {guidance && (
          <Callout.Text>
            {guidance.suggestion}
            {recommended && ` Parece más seguro o verosímil el registro de ${recommended.authorName}.`}
          </Callout.Text>
        )}
        {guidance && guidance.evidence.length > 0 && (
          <Flex direction="column" gap="1">
            <Text size="2" weight="medium">
              Exámenes relevantes del paciente:
            </Text>
            <Flex gap="2" wrap="wrap">
              {guidance.evidence.map((line) => (
                <Badge key={line} color="gray" variant="surface">
                  {line}
                </Badge>
              ))}
            </Flex>
          </Flex>
        )}
        {guidance?.externalRecommended && (
          <Callout.Text>
            <strong>Profesional adicional recomendado:</strong>{" "}
            {candidate
              ? `${candidate.name} (${professionLabel(candidate.profession)}), que está de turno.`
              : `${guidance.externalProfession ? professionLabel(guidance.externalProfession) : "Otro profesional"}, pero hoy no hay nadie adecuado de turno.`}{" "}
            {guidance.externalReason} Se le informará el caso sin datos del paciente ni de ustedes.
          </Callout.Text>
        )}
        {guidance?.externalRecommended && candidate && canAsk && (
          <Flex>
            <Button size="1" variant="soft" disabled={asked} loading={act.isPending} onClick={() => act.mutate({ conflictId: conflict.id, action: "external" })}>
              {asked ? `Opinión ya pedida a ${candidate.name}` : `Pedir su opinión (anonimizada)`}
            </Button>
          </Flex>
        )}
        {act.isError && (
          <Text size="2" color="red">
            {act.error.message}
          </Text>
        )}
        {conflict.consults.map((consult) => (
          <Text key={consult.id} size="1" color="gray">
            Opinión externa de {consult.consultantName}
            {consult.consultantProfession && ` (${professionLabel(consult.consultantProfession)})`}:{" "}
            {consult.status === "answered" ? "respondió (ver notas)" : "pendiente"}
          </Text>
        ))}
      </Flex>
    </Callout.Root>
  );
}

/** La conversación del conflicto: queda el registro de las razones de cada profesional. */
function Notes({ conflict }: { conflict: Conflict }) {
  const act = useConflictAction();
  const [body, setBody] = useState("");
  const canWrite = conflict.myRole !== null && conflict.iAmOnShift && conflict.status === "open";

  return (
    <Flex
      direction="column"
      gap="2"
      p="3"
      style={{ borderRadius: "var(--radius-3)", background: "var(--gray-a2)", alignSelf: "stretch" }}
    >
      <Flex justify="between" align="center">
        <Text size="2" weight="medium">
          Notas y razones
        </Text>
        {conflict.notes.length > 0 && (
          <Text size="1" color="gray">
            {conflict.notes.length}
          </Text>
        )}
      </Flex>
      {conflict.notes.length === 0 ? (
        <Text size="1" color="gray">
          Todavía no hay notas.
        </Text>
      ) : (
        <Flex direction="column" gap="2">
          {conflict.notes.map((note) => (
            <NoteRow key={note.id} note={note} />
          ))}
        </Flex>
      )}
      {canWrite && (
        <Flex direction="column" gap="2" mt="auto" pt="2">
          <TextArea
            size="1"
            placeholder="Explica tu razón o responde al otro profesional…"
            value={body}
            onChange={(event) => setBody(event.target.value)}
          />
          <Flex>
            <Button
              size="1"
              variant="soft"
              disabled={!body.trim()}
              loading={act.isPending}
              onClick={() => act.mutate({ conflictId: conflict.id, action: "notes", body: { body: body.trim() } }, { onSuccess: () => setBody("") })}
            >
              Agregar nota
            </Button>
          </Flex>
        </Flex>
      )}
    </Flex>
  );
}

function NoteRow({ note }: { note: ConflictNote }) {
  const system = note.kind === "system";
  return (
    <Flex
      direction="column"
      gap="1"
      p={system ? "0" : "2"}
      style={{ borderRadius: "var(--radius-2)", background: system ? "transparent" : "var(--color-panel-solid)" }}
    >
      <Text size="1" color="gray">
        {system ? "Agente" : note.authorName}
        {note.kind === "external" && " · Opinión externa"}
        {note.profession && !system && ` · ${professionLabel(note.profession)}`} · {DATE_FORMAT.format(new Date(note.created_at))}
      </Text>
      <Text size="2" color={system ? "gray" : undefined} style={{ fontStyle: system ? "italic" : undefined }}>
        {note.body}
      </Text>
    </Flex>
  );
}
