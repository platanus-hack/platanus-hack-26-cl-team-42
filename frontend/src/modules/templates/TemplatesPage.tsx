import { Badge, Card, Flex, Grid, Heading, Text, TextField } from "@radix-ui/themes";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { useReportTemplates } from "./api";

export function TemplatesPage() {
  const { data: templates = [], isPending } = useReportTemplates();

  return (
    <ModulePage stepId="templates">
      <Grid columns={{ initial: "1", md: "280px 1fr" }} gap="4">
        <Flex direction="column" gap="3">
          <Heading size="4">Plantillas</Heading>
          {!isPending && templates.length === 0 ? (
            <EmptyState
              title="Sin plantillas"
              description="Las plantillas de informe disponibles aparecerán aquí."
            />
          ) : (
            templates.map((template) => (
              <Card key={template.id}>
                <Text weight="medium">{template.name}</Text>
              </Card>
            ))
          )}
        </Flex>

        <Card>
          <Flex direction="column" gap="4">
            <Flex direction="column" gap="1">
              <Heading size="4">Campos extraídos</Heading>
              <Text size="2" color="gray">
                Cada campo se completa con el texto transcrito. Revise los valores antes de continuar.
              </Text>
            </Flex>
            <Text size="2" color="gray">
              Seleccione una plantilla para ver sus campos.
            </Text>
            <Flex direction="column" gap="3">
              <Flex align="center" gap="2">
                <Text size="2" weight="medium">
                  Ejemplo de campo
                </Text>
                <Badge color="gray" variant="soft">
                  Requerido
                </Badge>
              </Flex>
              <TextField.Root placeholder="Valor extraído del texto" disabled />
            </Flex>
          </Flex>
        </Card>
      </Grid>
    </ModulePage>
  );
}
