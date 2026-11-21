import { Badge, Button, Card, Flex, Switch, Text } from "@radix-ui/themes";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { useActionables, type ActionableStatus } from "./api";

const STATUS_LABEL: Record<ActionableStatus, { label: string; color: "gray" | "blue" | "green" }> = {
  suggested: { label: "Sugerido", color: "gray" },
  active: { label: "Activo", color: "blue" },
  done: { label: "Completado", color: "green" },
};

export function ActionablesPage() {
  const { data: actionables = [], isPending } = useActionables();

  return (
    <ModulePage stepId="actionables">
      <Text size="2" color="gray">
        Los accionables son tareas o recomendaciones derivadas del informe consolidado. Active solo los que deban
        ejecutarse.
      </Text>

      {!isPending && actionables.length === 0 ? (
        <EmptyState
          title="Sin accionables sugeridos"
          description="Cuando exista un informe consolidado, sus accionables sugeridos aparecerán aquí."
        />
      ) : (
        <Flex direction="column" gap="3">
          {actionables.map((actionable) => (
            <Card key={actionable.id}>
              <Flex align="center" justify="between" gap="4" wrap="wrap">
                <Flex direction="column" gap="1">
                  <Flex align="center" gap="2">
                    <Text weight="medium">{actionable.title}</Text>
                    <Badge color={STATUS_LABEL[actionable.status].color} variant="soft">
                      {STATUS_LABEL[actionable.status].label}
                    </Badge>
                  </Flex>
                  <Text size="2" color="gray">
                    {actionable.description}
                  </Text>
                  <Text size="1" color="gray">
                    Origen: {actionable.sourceSection}
                  </Text>
                </Flex>
                <Switch disabled checked={actionable.status !== "suggested"} aria-label="Activar" />
              </Flex>
            </Card>
          ))}
          <Flex justify="end">
            <Button disabled>Activar seleccionados</Button>
          </Flex>
        </Flex>
      )}
    </ModulePage>
  );
}
