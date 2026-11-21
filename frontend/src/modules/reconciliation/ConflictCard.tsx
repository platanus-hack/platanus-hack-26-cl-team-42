import { useState } from "react";
import { Badge, Button, Callout, Card, Flex, Grid, Select, Text, TextArea, TextField } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { professionLabel } from "../recordings/professions";
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

/** Un choque entre dos informes: qué se contradice, por qué, y cómo resolverlo entre los dos. */
export function ConflictCard({ conflict, patientId, reportId }: { conflict: Conflict; patientId: number; reportId: string }) {
  const resolved = conflict.status === "resolved";
  return (
    <Card variant="surface">
      <Flex direction="column" gap="3">
        <Flex justify="between" align="center" gap="2" wrap="wrap">
          <Flex align="center" gap="2" wrap="wrap">
            <Text weight="medium">{conflict.label}</Text>
            <Badge color={conflict.kind === "allergy" ? "red" : "amber"} variant="soft">
              {conflict.kind === "allergy" ? "Riesgo de seguridad" : "Dato distinto"}
            </Badge>
          </Flex>
          <Badge color={resolved ? "green" : "orange"} variant="soft">
            {resolved ? "Resuelto" : "Por resolver"}
          </Badge>
        </Flex>

        <Callout.Root color={conflict.kind === "allergy" ? "red" : "amber"} size="1">
          <Callout.Text>
            <strong>Agente:</strong> {conflict.explanation}
          </Callout.Text>
        </Callout.Root>

        <Flex gap="2" wrap="wrap">
          {conflict.participantsShift.map((participant) => (
            <Badge key={participant.name} color={participant.onShift ? "green" : "gray"} variant="soft">
              {participant.name} · {participant.onShift ? "de turno" : "fuera de turno"}
            </Badge>
          ))}
        </Flex>

        <Grid columns={{ initial: "1", sm: "2" }} gap="3">
          <SideBox side={conflict.sideA} mine={conflict.myRole === "a" || conflict.myRole === "both"} chosen={resolved && conflict.resolution?.side === "a"} />
          <SideBox side={conflict.sideB} mine={conflict.myRole === "b" || conflict.myRole === "both"} chosen={resolved && conflict.resolution?.side === "b"} />
        </Grid>

        <Link
          to="/"
          search={{ patient: String(patientId), report: conflict.sideB.reportId ?? reportId, section: conflict.section }}
          style={{ fontSize: "var(--font-size-1)" }}
        >
          Ver la sección «{sectionLabel(conflict.section)}» en el informe
        </Link>

        <AgentGuidance conflict={conflict} />

        {resolved && conflict.resolution ? <ResolutionSummary resolution={conflict.resolution} /> : <Actions conflict={conflict} />}

        <Notes conflict={conflict} />
      </Flex>
    </Card>
  );
}

function SideBox({ side, mine, chosen }: { side: ConflictSide; mine: boolean; chosen: boolean }) {
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
          <Badge color="indigo" variant="soft" size="1">
            Tu registro
          </Badge>
        )}
        {chosen && (
          <Badge color="green" variant="soft" size="1">
            Elegido
          </Badge>
        )}
      </Flex>
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

/** Aceptar el valor del otro, proponer (consenso) o, si el otro terminó su turno, decidir. */
function Actions({ conflict }: { conflict: Conflict }) {
  const act = useConflictAction();
  const [choice, setChoice] = useState<"mine" | "other" | "custom">("custom");
  const [custom, setCustom] = useState("");

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
  const mySide = conflict.myRole === "b" ? "b" : "a";
  const otherSide = mySide === "a" ? "b" : "a";
  const other = conflict.myRole === "both" ? null : otherSide === "a" ? conflict.sideA : conflict.sideB;
  const proposeBody = () =>
    choice === "custom" ? { value: custom.trim() } : { side: (choice === "mine" ? mySide : otherSide) as "a" | "b" };
  const canPropose = conflict.myRole !== "both" && (choice !== "custom" || (conflict.kind === "value" && custom.trim() !== ""));

  return (
    <Flex direction="column" gap="3">
      {conflict.proposal && (
        <Callout.Root color="blue" size="1">
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

      <Flex gap="2" wrap="wrap" align="center">
        {conflict.canAccept && other && (
          <Button loading={act.isPending} onClick={() => act.mutate({ conflictId: conflict.id, action: "accept" })}>
            Aceptar el valor de {other.authorName}
          </Button>
        )}
        {conflict.canDecide && (
          <>
            <Button
              variant="soft"
              loading={act.isPending}
              onClick={() => act.mutate({ conflictId: conflict.id, action: "decide", body: { side: mySide } })}
            >
              Decidir: mantener mi valor
            </Button>
            {other && (
              <Button
                variant="soft"
                loading={act.isPending}
                onClick={() => act.mutate({ conflictId: conflict.id, action: "decide", body: { side: otherSide } })}
              >
                Decidir: usar el del otro
              </Button>
            )}
          </>
        )}
      </Flex>
      {conflict.canDecide && other && (
        <Callout.Root color="amber" size="1">
          <Callout.Text>
            <strong>
              {other.authorName} ({professionLabel(other.profession)})
            </strong>{" "}
            está fuera de turno y no puede participar. Había registrado «{other.value}». Puedes decidir tú, sabiendo que
            existe esta discrepancia: quedará anotado que decidiste con conocimiento de lo que él o ella reportó.
          </Callout.Text>
        </Callout.Root>
      )}
      {!conflict.canDecide && conflict.myRole !== "both" && (
        <Text size="1" color="gray">
          El otro profesional sigue de turno: acepta su valor o propón una solución para llegar a consenso.
        </Text>
      )}

      {conflict.myRole !== "both" && (
        <Flex gap="2" wrap="wrap" align="center">
          <Select.Root value={choice} onValueChange={(value) => setChoice(value as typeof choice)}>
            <Select.Trigger />
            <Select.Content>
              <Select.Item value="mine">Proponer mi valor</Select.Item>
              <Select.Item value="other">Proponer el del otro</Select.Item>
              {conflict.kind === "value" && <Select.Item value="custom">Proponer otro valor…</Select.Item>}
            </Select.Content>
          </Select.Root>
          {choice === "custom" && conflict.kind === "value" && (
            <TextField.Root placeholder="Valor propuesto" value={custom} onChange={(event) => setCustom(event.target.value)} />
          )}
          <Button
            variant="soft"
            disabled={!canPropose}
            loading={act.isPending}
            onClick={() => act.mutate({ conflictId: conflict.id, action: "propose", body: proposeBody() })}
          >
            Proponer
          </Button>
        </Flex>
      )}

      {act.isError && (
        <Text size="2" color="red">
          {act.error.message}
        </Text>
      )}
    </Flex>
  );
}

/** Orientación del agente (ya generada) y el profesional de turno que el sistema recomienda consultar. */
function AgentGuidance({ conflict }: { conflict: Conflict }) {
  const act = useConflictAction();
  const guidance = conflict.guidance;
  if (!guidance) return null;
  const candidate = guidance.externalCandidate;
  const asked = candidate !== null && conflict.consults.some((consult) => consult.consultantName === candidate.name);
  const recommended =
    guidance.recommendedSide === "none" ? null : guidance.recommendedSide === "a" ? conflict.sideA : conflict.sideB;
  const canAsk = conflict.status === "open" && conflict.iAmOnShift && conflict.myRole !== null;

  return (
    <Callout.Root color="indigo" size="1">
      <Flex direction="column" gap="2">
        <Callout.Text>
          <strong>Orientación del agente:</strong> {guidance.suggestion}
          {recommended && ` Parece más seguro o verosímil el registro de ${recommended.authorName}.`}
        </Callout.Text>
        {guidance.evidence.length > 0 && (
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
        {guidance.externalRecommended && (
          <Callout.Text>
            <strong>Profesional adicional recomendado:</strong>{" "}
            {candidate
              ? `${candidate.name} (${professionLabel(candidate.profession)}), que está de turno.`
              : `${guidance.externalProfession ? professionLabel(guidance.externalProfession) : "Otro profesional"}, pero hoy no hay nadie adecuado de turno.`}{" "}
            {guidance.externalReason} Se le informará el caso sin datos del paciente ni de ustedes.
          </Callout.Text>
        )}
        {guidance.externalRecommended && candidate && canAsk && (
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
    <Flex direction="column" gap="2">
      <Text size="2" weight="medium">
        Notas y razones
      </Text>
      <Flex direction="column" gap="1">
        {conflict.notes.map((note) => (
          <NoteRow key={note.id} note={note} />
        ))}
      </Flex>
      {canWrite && (
        <Flex direction="column" gap="2">
          <TextArea placeholder="Explica tu razón o responde al otro profesional…" value={body} onChange={(event) => setBody(event.target.value)} />
          <Flex>
            <Button
              size="1"
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
    <Flex direction="column" p="2" style={{ borderRadius: "var(--radius-2)", background: system ? "transparent" : "var(--gray-a2)" }}>
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
