import { useState } from "react";
import { Button, Callout, Dialog, Flex, Select, Text, TextArea, TextField } from "@radix-ui/themes";
import type { FieldSchema } from "../templates/api";
import { resolveField, sectionLabel } from "../templates/recordFields";
import { useEditReportItem, type Report } from "./api";

interface ItemEditorProps {
  report: Report;
  section: string;
  index?: number;
  value: unknown;
  schema: FieldSchema;
  definitions: Record<string, FieldSchema>;
  disabled: boolean;
}

export function EditReportItem(props: ItemEditorProps) {
  const [open, setOpen] = useState(false);
  const edit = useEditReportItem();
  const label = props.index === undefined
    ? sectionLabel(props.section)
    : `${sectionLabel(props.section)} · ítem ${props.index + 1}`;

  return (
    <Dialog.Root open={open} onOpenChange={(next) => {
      if (!edit.isPending) {
        edit.reset();
        setOpen(next);
      }
    }}>
      <Dialog.Trigger>
        <Button variant="soft" size="1" disabled={props.disabled} aria-label={`Editar ${label}`}>
          Editar
        </Button>
      </Dialog.Trigger>
      <Dialog.Content maxWidth="520px">
        <Dialog.Title>Editar {label}</Dialog.Title>
        <Dialog.Description size="2" color="gray">Los cambios se aplican a este borrador.</Dialog.Description>
        {open && <ItemForm {...props} label={label} edit={edit} onDone={() => setOpen(false)} />}
      </Dialog.Content>
    </Dialog.Root>
  );
}

function ItemForm({ report, section, index, value, schema, definitions, label, edit, onDone }: ItemEditorProps & {
  label: string;
  edit: ReturnType<typeof useEditReportItem>;
  onDone: () => void;
}) {
  const [initial] = useState(() => ({ value, revision: report.editRevision }));
  const [draft, setDraft] = useState(initial.value);
  const dirty = JSON.stringify(initial.value) !== JSON.stringify(draft);

  return (
    <form onSubmit={(event) => {
      event.preventDefault();
      if (dirty && !edit.isPending) {
        edit.mutate(
          { reportId: report.id, section, index, value: draft, revision: initial.revision },
          { onSuccess: onDone },
        );
      }
    }}>
      <Flex direction="column" gap="3" mt="3">
        <EditField label={label} value={draft} schema={schema} definitions={definitions} onChange={setDraft} />
        {edit.isError && (
          <Callout.Root size="1" color="red" role="alert">
            <Callout.Text>{edit.error.message}</Callout.Text>
          </Callout.Root>
        )}
        <Flex justify="end" gap="2" wrap="wrap">
          <Dialog.Close>
            <Button type="button" variant="soft" color="gray" disabled={edit.isPending}>Cancelar</Button>
          </Dialog.Close>
          <Button type="submit" loading={edit.isPending} disabled={!dirty}>Guardar cambios</Button>
        </Flex>
      </Flex>
    </form>
  );
}

interface EditFieldProps {
  label: string;
  value: unknown;
  schema: FieldSchema;
  definitions: Record<string, FieldSchema>;
  onChange: (value: unknown) => void;
}

function EditField({ label, value, schema, definitions, onChange }: EditFieldProps) {
  const { field, nullable } = resolveField(schema, definitions);
  const properties = field.properties;
  if (properties) {
    if (value == null) {
      return (
        <Flex align="center" justify="between" gap="2">
          <Text size="2">{label}</Text>
          <Button type="button" size="1" variant="soft" onClick={() => onChange(initialObject(properties, definitions))}>
            Completar
          </Button>
        </Flex>
      );
    }
    const data = value as Record<string, unknown>;
    return (
      <Flex direction="column" gap="3" role="group" aria-label={label}>
        {Object.entries(properties).map(([key, child]) => key === "evidencia" ? (
          data[key] ? <Text key={key} size="2" color="gray">Cita del dictado · {String(data[key])}</Text> : null
        ) : (
          <EditField key={key} label={sectionLabel(key)} value={data[key]} schema={child} definitions={definitions}
            onChange={(next) => onChange({ ...data, [key]: next })} />
        ))}
      </Flex>
    );
  }

  if (field.items) {
    const items = Array.isArray(value) ? value : [];
    const itemSchema = field.items;
    return (
      <Flex direction="column" gap="2" role="group" aria-label={label}>
        <Text size="2" weight="medium">{label}</Text>
        {items.map((item, index) => (
          <EditField key={index} label={`${label} · ítem ${index + 1}`} value={item} schema={itemSchema}
            definitions={definitions} onChange={(next) => onChange(items.map((old, i) => i === index ? next : old))} />
        ))}
        <Button type="button" variant="soft" size="1" onClick={() => onChange([...items, initialValue(itemSchema, definitions)])}>
          Agregar valor
        </Button>
      </Flex>
    );
  }

  const types = Array.isArray(field.type) ? field.type : [field.type];
  const choices = field.enum ?? (types.includes("boolean") ? [true, false, ...(nullable ? [null] : [])] : undefined);
  if (choices) {
    const selected = choices.indexOf((value ?? null) as typeof choices[number]);
    return (
      <Flex direction="column" gap="1">
        <Text size="2" weight="medium">{label}</Text>
        <Select.Root value={selected < 0 ? "" : String(selected)} onValueChange={(choice) => onChange(choices[Number(choice)])}>
          <Select.Trigger aria-label={label} placeholder="Seleccionar" />
          <Select.Content>
            {choices.map((choice, index) => <Select.Item key={index} value={String(index)}>{choiceLabel(choice)}</Select.Item>)}
          </Select.Content>
        </Select.Root>
      </Flex>
    );
  }

  const number = types.includes("number") || types.includes("integer");
  const shown = typeof value === "string" || typeof value === "number" ? String(value) : "";
  const update = (text: string) => onChange(text === "" && nullable ? null : number && text !== "" ? Number(text) : text);
  return (
    <Flex direction="column" gap="1">
      <Text size="2" weight="medium">{label}</Text>
      {number ? (
        <TextField.Root aria-label={label} type="number" step={types.includes("integer") ? 1 : "any"}
          min={field.minimum} max={field.maximum} value={shown} onChange={(event) => update(event.target.value)} />
      ) : (
        <TextArea aria-label={label} rows={2} value={shown} onChange={(event) => update(event.target.value)} />
      )}
    </Flex>
  );
}

function choiceLabel(choice: string | number | boolean | null) {
  if (choice === null) return "Sin informar";
  if (typeof choice === "boolean") return choice ? "Sí" : "No";
  return typeof choice === "string" ? sectionLabel(choice) : String(choice);
}

function initialObject(properties: Record<string, FieldSchema>, definitions: Record<string, FieldSchema>) {
  return Object.fromEntries(Object.entries(properties).map(([key, schema]) => [key, initialValue(schema, definitions)]));
}

function initialValue(schema: FieldSchema, definitions: Record<string, FieldSchema>): unknown {
  const { field, nullable } = resolveField(schema, definitions);
  if (nullable) return null;
  if (field.properties) return initialObject(field.properties, definitions);
  if (field.items) return [];
  return field.type === "string" && !field.enum ? "" : null;
}
