import { Badge, Button, Flex, Table, Text } from "@radix-ui/themes";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { professionLabel } from "../recordings/professions";
import { useConceptMappings, type ConceptStatus } from "./api";

const STATUS_LABEL: Record<ConceptStatus, { label: string; color: "gray" | "green" | "red" }> = {
  pending: { label: "Pendiente", color: "gray" },
  approved: { label: "Aprobado", color: "green" },
  rejected: { label: "Rechazado", color: "red" },
};

export function ConceptsPage() {
  const { data: mappings = [], isPending } = useConceptMappings();

  return (
    <ModulePage stepId="concepts" connected>
      <Text size="2" color="gray">
        Cada término de un profesional se propone como concepto canónico. Confirme o corrija la propuesta para que
        todos los informes usen el mismo vocabulario.
      </Text>

      {!isPending && mappings.length === 0 ? (
        <EmptyState
          title="Sin términos por homologar"
          description="Los términos detectados en los informes aparecerán aquí con su propuesta de concepto."
        />
      ) : (
        <Table.Root variant="surface">
          <Table.Header>
            <Table.Row>
              <Table.ColumnHeaderCell>Término original</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell>Profesional</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell>Concepto propuesto</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell>Estado</Table.ColumnHeaderCell>
              <Table.ColumnHeaderCell />
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {mappings.map((mapping) => (
              <Table.Row key={mapping.id}>
                <Table.Cell>{mapping.sourceTerm}</Table.Cell>
                <Table.Cell>{mapping.sourceProfessional ? professionLabel(mapping.sourceProfessional) : "Diccionario base"}</Table.Cell>
                <Table.Cell>{mapping.approvedConcept ?? mapping.suggestedConcept ?? "—"}</Table.Cell>
                <Table.Cell>
                  <Badge color={STATUS_LABEL[mapping.status].color} variant="soft">
                    {STATUS_LABEL[mapping.status].label}
                  </Badge>
                </Table.Cell>
                <Table.Cell>
                  <Flex justify="end">
                    <Button size="1" variant="soft" disabled>
                      Aprobar
                    </Button>
                  </Flex>
                </Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table.Root>
      )}
    </ModulePage>
  );
}
