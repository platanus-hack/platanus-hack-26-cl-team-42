import { useState, type ReactNode } from "react";
import { Badge, Button, Callout, Code, Flex, Heading, Text } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { formatClinicalTime } from "./format";
import type { Episode, OpenConflict, PendingTask } from "./model";

/** Marca visible de que todo lo que sigue es un episodio ficticio. */
export function DemoEpisodeBanner({ episode, children }: { episode: Episode; children?: ReactNode }) {
  return (
    <Callout.Root color="amber" variant="surface">
      <Flex align="center" justify="between" gap="3" wrap="wrap">
        <Callout.Text>
          <strong>Episodio ficticio · datos de demostración.</strong> {episode.label} · {episode.unit} ·
          episodio <Code variant="ghost">{episode.id}</Code> · corte {formatClinicalTime(episode.cutoffAt)}
        </Callout.Text>
        {children}
      </Flex>
    </Callout.Root>
  );
}

/** Enlace real a la atención de origen dentro del registro clínico. */
export function SourceLink({
  episodeId,
  encounterId,
  children,
}: {
  episodeId: string;
  encounterId: string;
  children: ReactNode;
}) {
  return (
    <Link to="/official-form" search={{ episode: episodeId, encounter: encounterId }}>
      {children}
    </Link>
  );
}

export function OpenConflicts({ episodeId, conflicts }: { episodeId: string; conflicts: OpenConflict[] }) {
  if (conflicts.length === 0) return null;

  return (
    <Callout.Root color="amber" variant="soft">
      <Flex direction="column" gap="2">
        <Heading size="3">Conflictos por revisar</Heading>
        {conflicts.map((conflict) => (
          <Flex key={conflict.id} direction="column" gap="1">
            <Callout.Text>{conflict.description}</Callout.Text>
            <Flex gap="2" wrap="wrap">
              {conflict.sourceEncounterIds.map((id, index) => (
                <SourceLink key={id} episodeId={episodeId} encounterId={id}>
                  {conflict.sourceEncounterIds.length === 1 ? "Ver atención de origen" : `Ver atención ${index + 1}`}
                </SourceLink>
              ))}
            </Flex>
          </Flex>
        ))}
      </Flex>
    </Callout.Root>
  );
}

export function PendingStatusBadge({ status }: { status: PendingTask["status"] }) {
  return status === "open" ? (
    <Badge color="orange" variant="soft">
      Abierto
    </Badge>
  ) : (
    <Badge color="green" variant="soft">
      Cerrado
    </Badge>
  );
}

type CopyState = "idle" | "copied" | "failed";

export function CopyButton({ text, label = "Copiar texto" }: { text: string; label?: string }) {
  const [state, setState] = useState<CopyState>("idle");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
  };
  return (
    <Flex align="center" gap="2">
      {state === "failed" && (
        <Text size="1" color="red">
          No se pudo copiar: selecciona el texto manualmente.
        </Text>
      )}
      <Button variant="soft" onClick={copy}>
        {state === "copied" ? "Copiado" : label}
      </Button>
    </Flex>
  );
}
