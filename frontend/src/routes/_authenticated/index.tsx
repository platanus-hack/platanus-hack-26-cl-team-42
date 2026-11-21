import { createFileRoute } from "@tanstack/react-router";
import { Box, Flex, Heading, Text } from "@radix-ui/themes";
import { useAuth } from "../../services/auth";
import { PipelineOverview } from "../../components/PipelineOverview";
import { WORKFLOW_STEPS } from "../../config/workflow";

export const Route = createFileRoute("/_authenticated/")({
  component: HomePage,
});

function HomePage() {
  const { session } = useAuth();
  const userName = session?.display || session?.email?.split("@")[0] || "";

  return (
    <Flex direction="column" gap="6" p={{ initial: "4", md: "6" }} style={{ maxWidth: "1100px" }}>
      <Box className="hero" p={{ initial: "5", md: "6" }} style={{ borderRadius: "var(--radius-5)" }}>
        <Flex direction="column" gap="3">
          <Text size="2" color="teal" weight="medium">
            Bienvenido{userName ? `, ${userName}` : ""}
          </Text>
          <Heading size="8" style={{ letterSpacing: "-0.02em", lineHeight: 1.1 }}>
            De la grabación a la ficha oficial
          </Heading>
          <Text color="gray" size="3" style={{ maxWidth: 620 }}>
            Reúna los dictados de cada profesional, conviértalos en un informe único y traspase el caso cuando esté
            listo.
          </Text>
          <Flex gap="4" mt="2" wrap="wrap">
            <Stat label="Pasos en el flujo" value={String(WORKFLOW_STEPS.length)} />
            <Stat label="Módulos conectados" value="0" />
          </Flex>
        </Flex>
      </Box>

      <Flex direction="column" gap="3">
        <Heading size="4">Flujo de trabajo</Heading>
        <PipelineOverview />
      </Flex>
    </Flex>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Flex direction="column" gap="0" px="4" py="3" style={{ background: "var(--color-panel-solid)", borderRadius: "var(--radius-4)", minWidth: 150, boxShadow: "0 1px 2px var(--gray-a4)" }}>
      <Text size="6" weight="bold" style={{ fontVariantNumeric: "tabular-nums" }}>
        {value}
      </Text>
      <Text size="1" color="gray">
        {label}
      </Text>
    </Flex>
  );
}
