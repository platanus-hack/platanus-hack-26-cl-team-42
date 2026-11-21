import { Badge, Button, Card, Flex, Grid, Heading, Select, Text, TextArea } from "@radix-ui/themes";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { useHandoffs, type HandoffStatus } from "./api";

const STATUS_LABEL: Record<HandoffStatus, { label: string; color: "blue" | "green" | "orange" }> = {
  sent: { label: "Enviado", color: "blue" },
  accepted: { label: "Aceptado", color: "green" },
  returned: { label: "Devuelto", color: "orange" },
};

export function HandoffPage() {
  const { data: handoffs = [], isPending } = useHandoffs();

  return (
    <ModulePage stepId="handoff">
      <Grid columns={{ initial: "1", md: "1fr 1fr" }} gap="4">
        <Card>
          <Flex direction="column" gap="3">
            <Heading size="4">Nuevo traspaso</Heading>
            <Select.Root disabled>
              <Select.Trigger placeholder="Persona destinataria" style={{ width: "100%" }} />
              <Select.Content />
            </Select.Root>
            <TextArea disabled placeholder="Nota para la persona que recibe el caso" rows={5} />
            <Flex justify="end">
              <Button disabled>Traspasar caso</Button>
            </Flex>
          </Flex>
        </Card>

        <Flex direction="column" gap="3">
          <Heading size="4">Traspasos realizados</Heading>
          {!isPending && handoffs.length === 0 ? (
            <EmptyState
              title="Sin traspasos"
              description="Los casos traspasados a otras personas aparecerán aquí con su estado."
            />
          ) : (
            handoffs.map((handoff) => (
              <Card key={handoff.id}>
                <Flex direction="column" gap="1">
                  <Flex align="center" justify="between" gap="2">
                    <Text weight="medium">{handoff.recipient.name}</Text>
                    <Badge color={STATUS_LABEL[handoff.status].color} variant="soft">
                      {STATUS_LABEL[handoff.status].label}
                    </Badge>
                  </Flex>
                  <Text size="2" color="gray">
                    {handoff.recipient.role} · {handoff.createdAt}
                  </Text>
                </Flex>
              </Card>
            ))
          )}
        </Flex>
      </Grid>
    </ModulePage>
  );
}
