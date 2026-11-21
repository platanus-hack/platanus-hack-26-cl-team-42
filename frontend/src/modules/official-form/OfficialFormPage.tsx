import { Badge, Button, Card, Flex, Heading, Text, TextArea, TextField } from "@radix-ui/themes";
import { ModulePage } from "../../components/ModulePage";
import { EmptyState } from "../../components/EmptyState";
import { useOfficialForm } from "./api";

export function OfficialFormPage() {
  const { data: form, isPending } = useOfficialForm();

  if (!isPending && !form) {
    return (
      <ModulePage stepId="official-form">
        <EmptyState
          title="Sin ficha activa"
          description="Cuando haya un informe consolidado, la ficha oficial correspondiente se cargará aquí."
        />
      </ModulePage>
    );
  }

  return (
    <ModulePage stepId="official-form">
      <Card>
        <Flex direction="column" gap="4">
          <Flex align="center" justify="between" gap="3" wrap="wrap">
            <Heading size="4">{form?.title ?? "Ficha oficial"}</Heading>
            <Badge color="gray" variant="soft">
              Borrador
            </Badge>
          </Flex>
          {form?.fields.map((field) => (
            <Flex key={field.key} direction="column" gap="1">
              <Text size="2" weight="medium">
                {field.label}
                {field.required ? " *" : ""}
              </Text>
              {field.value.length > 120 ? (
                <TextArea disabled value={field.value} />
              ) : (
                <TextField.Root disabled value={field.value} />
              )}
            </Flex>
          ))}
          <Flex justify="end" gap="3">
            <Button variant="soft" disabled>
              Guardar borrador
            </Button>
            <Button disabled>Enviar ficha</Button>
          </Flex>
        </Flex>
      </Card>
    </ModulePage>
  );
}
