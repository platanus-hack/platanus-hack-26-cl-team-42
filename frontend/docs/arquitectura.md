# Arquitectura del frontend

Base visual de la aplicación. Ningún módulo está implementado todavía: las
pantallas se muestran con sus estados vacíos y los controles deshabilitados, y
la capa de conexiones está definida pero sin backend detrás.

## Flujo

```
Grabar audio → Transcribir → Parseo a plantillas → Homologar conceptos
      → Consolidar informes → Activar accionables → Ficha oficial → Traspaso
```

El orden vive en un único lugar: `src/config/workflow.ts`. La barra lateral,
la vista de inicio y el pie de cada módulo (anterior / siguiente) lo leen de ahí.

## Estructura

```
src/
├── config/workflow.ts          Pasos del flujo (fuente única de orden y rutas)
├── components/                 Piezas compartidas (ModulePage, EmptyState, Sidebar…)
├── services/
│   ├── api/client.ts           Cliente HTTP común (apiRequest, notConnected)
│   ├── auth/                   Autenticación (allauth) — sin cambios
│   └── language.ts             Idioma activo, enviado como Accept-Language
├── modules/<módulo>/
│   ├── api.ts                  Contrato del módulo: tipos, gateway, hooks
│   └── <Módulo>Page.tsx        Pantalla del módulo
└── routes/_authenticated/
    ├── index.tsx               Inicio
    └── <módulo>.tsx            Ruta fina: solo importa la página del módulo
```

Cada módulo tiene dos archivos. Las rutas no contienen lógica.

## Capa de conexiones

Cada módulo expone un **gateway**: una interfaz con las operaciones que
necesita, más un adaptador concreto.

```ts
export interface RecordingsGateway {
  list(): Promise<Recording[]>;
  upload(audio: Blob): Promise<Recording>;
  remove(id: string): Promise<void>;
}

export const recordingsGateway: RecordingsGateway = {
  list: async () => [],                       // lectura: vacío
  upload: notConnected("recordings.upload"),  // escritura: falla explícitamente
  remove: notConnected("recordings.remove"),
};
```

Las pantallas no llaman al gateway directamente: usan los hooks de React Query
del mismo `api.ts` (`useRecordings`, `useUploadRecording`, …). Así, cuando un
backend exista, basta con reemplazar el adaptador por uno que use
`apiRequest("/recordings/…")` sin tocar las pantallas.

Convenciones:

- **Prefijo de API:** `/-/api/<módulo>/`, el mismo que usa el resto del proyecto.
- **Claves de caché:** una constante por módulo (`recordingKeys`, …); las
  mutaciones invalidan su clave.
- **Errores:** `ApiError` para respuestas HTTP con error; `NotConnectedError`
  mientras el backend del módulo no existe.
- **Referencias entre módulos:** por `id`. Un `Transcript` guarda el
  `recordingId`, un `ParsedReport` el `transcriptId`, y así sucesivamente. Ningún
  módulo importa tipos de otro salvo para leer esa referencia.

## Estados de cada pantalla

- Lista vacía: `EmptyState` con texto explicando qué aparecerá ahí.
- Controles: deshabilitados, con la etiqueta de la acción que van a ejecutar.
- Encabezado: insignia "Sin conexión" hasta que el módulo tenga backend.

## Pendiente

- Decidir si la selección de **caso** (un paciente o expediente agrupa los
  informes de varios profesionales) entra como parámetro de ruta o como
  contexto global. Hoy las listas no están acotadas a un caso.
- Backend: `backend/apps/demo` y `backend/lib/tracker` siguen existiendo. El
  frontend ya no los usa; retirarlos toca `conf/settings.py`, `conf/urls.py`,
  `conf/celery.py` y varios tests, así que se hará en un cambio aparte.
- Implementar cada gateway contra su backend, módulo por módulo.
