import { Badge, Button, Callout, Card, Flex, Heading, Spinner, Text } from "@radix-ui/themes";
import { createFileRoute } from "@tanstack/react-router";
import { accountTypeLabel, useAccountProfile } from "../../../modules/account/api";
import { professionLabel } from "../../../modules/recordings/professions";

export const Route = createFileRoute("/_authenticated/profile/")({
  component: ProfilePage,
});

export function ProfilePage() {
  const { data: profile, isPending, isError } = useAccountProfile();

  return (
    <Flex direction="column" gap="4" style={{ maxWidth: 560 }}>
      <Heading size="6">Mi perfil</Heading>
      {isPending && <Spinner aria-label="Cargando perfil" />}
      {isError && (
        <Callout.Root color="red">
          <Callout.Text>No se pudo cargar tu perfil.</Callout.Text>
        </Callout.Root>
      )}
      {profile && (
        <Card size="3">
          <Flex direction="column" align="start" gap="3">
            <Flex direction="column" gap="1">
              <Heading size="4">{profile.name || profile.email}</Heading>
              {profile.name && <Text color="gray" size="2">{profile.email}</Text>}
            </Flex>
            <Badge color={profile.admin_url ? "indigo" : "gray"}>{accountTypeLabel(profile)}</Badge>
            <Text size="2">
              <strong>Profesión clínica</strong> · {profile.profession ? professionLabel(profile.profession) : "Sin definir"}
            </Text>
            <Text size="2" color="gray">
              El acceso a pacientes depende de las asignaciones de tu cuenta. En un conflicto, pueden resolver quienes
              reportaron los datos en disputa, tienen asignado al paciente y están de turno.
            </Text>
            {profile.admin_url && (
              <Button asChild variant="soft">
                <a href={profile.admin_url}>Ir a Administración</a>
              </Button>
            )}
          </Flex>
        </Card>
      )}
    </Flex>
  );
}
