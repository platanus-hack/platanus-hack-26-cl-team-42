import { Badge, Card, Flex, Grid, Heading, Text } from "@radix-ui/themes";
import { Link } from "@tanstack/react-router";
import { WORKFLOW_STEPS } from "../config/workflow";
import { ArrowIcon, StepIcon } from "./icons";

/** Vista general del flujo completo: una tarjeta por paso, en orden. */
export function PipelineOverview() {
  return (
    <Grid columns={{ initial: "1", sm: "2", lg: "4" }} gap="4">
      {WORKFLOW_STEPS.map((step, index) => (
        <Link key={step.id} to={step.path} style={{ textDecoration: "none", color: "inherit" }}>
          <Card size="3" className="flow-card">
            <Flex direction="column" gap="3" height="100%">
              <Flex align="center" justify="between">
                <span className="step-icon">
                  <StepIcon id={step.id} />
                </span>
                <Text size="1" color="gray" weight="medium" style={{ fontVariantNumeric: "tabular-nums" }}>
                  {String(index + 1).padStart(2, "0")}
                </Text>
              </Flex>
              <Flex direction="column" gap="1" style={{ flex: 1 }}>
                <Heading size="3">{step.label}</Heading>
                <Text size="2" color="gray">
                  {step.summary}
                </Text>
              </Flex>
              <Flex align="center" justify="between">
                <Badge color="gray" variant="surface" size="1" radius="full">
                  Sin conexión
                </Badge>
                <Text size="2" color="gray">
                  <ArrowIcon direction="right" size={16} />
                </Text>
              </Flex>
            </Flex>
          </Card>
        </Link>
      ))}
    </Grid>
  );
}
