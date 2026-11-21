import { Button, Card, Checkbox, Flex, Grid, Heading, Text } from "@radix-ui/themes";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { useProfessionalReports } from "./api";

export function ConsolidationPage() {
  const { data: reports = [], isPending } = useProfessionalReports();

  return (
    <ModulePage stepId="consolidation">
      <Grid columns={{ initial: "1", md: "1fr 1fr" }} gap="4">
        <Flex direction="column" gap="3">
          <Heading size="4">Informes de los profesionales</Heading>
          {!isPending && reports.length === 0 ? (
            <EmptyState
              title="Sin informes para consolidar"
              description="Los informes parseados de cada profesional aparecerán aquí para seleccionarlos."
            />
          ) : (
            reports.map((report) => (
              <Card key={report.id}>
                <Flex align="center" gap="3">
                  <Checkbox disabled />
                  <Flex direction="column">
                    <Text weight="medium">{report.professionalName}</Text>
                    <Text size="2" color="gray">
                      {report.specialty}
                    </Text>
                  </Flex>
                </Flex>
              </Card>
            ))
          )}
          <Button disabled>Consolidar seleccionados</Button>
        </Flex>

        <Card>
          <Flex direction="column" gap="3">
            <Heading size="4">Informe consolidado</Heading>
            <Text size="2" color="gray">
              Cada sección indica de qué informes proviene. Las diferencias entre profesionales quedan marcadas para revisión.
            </Text>
          </Flex>
        </Card>
      </Grid>
    </ModulePage>
  );
}
