# Testing: Transcripción + Extracción con Qwen

Este documento explica cómo probar el flujo completo de transcripción + extracción de información usando Qwen y templates clínicos.

## Arquitectura

```
Recording (Audio)
    ↓
Transcription (Whisper) ← Texto
    ↓
ExtractedRecord (Qwen + Template) ← JSON estructurado
```

### Componentes

**1. Transcription (Whisper ASR)**
- Convierte audio → texto
- Modelo: `openai/whisper-small`
- Resultado: `Transcription.text` (string)

**2. ExtractedRecord (Qwen LLM)**
- Extrae información estructurada del transcript
- Modelo: Qwen 2.5 1.5B (local) o Qwen 2.5 72B (Hugging Face)
- Validación: JSON Schema contra template clínico
- Resultado: `ExtractedRecord.data` (JSON estructurado)

**3. ClinicalTemplate**
- Define el schema JSON de salida
- Instrucciones LLM en español
- Versioning automático

## Preparar el entorno

### 1. Instalar dependencias nuevas

```bash
just local down
just local up
```

Esto reconstruye los contenedores con:
- `pyttsx3` para generar audios de ejemplo
- El nuevo modelo `ExtractedRecord` en la BD

### 2. Aplicar migración

```bash
docker exec backend python manage.py migrate transcription
```

Verifica que no hay errores:
```bash
docker exec backend python manage.py migrate transcription --plan
```

### 3. Cargar templates clínicos

```bash
docker exec backend python manage.py load_clinical_templates
```

Verifica:
```bash
docker exec backend python manage.py shell
>>> from apps.clinical_templates.models import ClinicalTemplate
>>> ClinicalTemplate.objects.count()  # Debe ser 5
>>> list(ClinicalTemplate.objects.values_list('slug', flat=True))
# ['enfermeria_uci', 'especialista_interconsulta', 'kinesiologia_uci', 'medico_uci', 'tens_uci']
```

## Generar audios de ejemplo

Los audios se generan con síntesis de voz en español para cada tipo de profesional.

### Generar archivos WAV

```bash
docker exec backend python manage.py generate_sample_audios
```

Resultado: Archivos `.wav` en `/app/apps/transcription/samples/`

```
samples/
├── medico_uci.wav
├── enfermeria_uci.wav
├── kinesiologia_uci.wav
├── tens_uci.wav
└── especialista_interconsulta.wav
```

### Cargar audios en la BD

```bash
# Sin esperar
docker exec backend python manage.py load_sample_audios

# O esperando a que se procesen
docker exec backend python manage.py load_sample_audios --wait-extraction
```

Parámetros:
- `--professional-email EMAIL` — Email del profesional (default: admin@example.com)
- `--wait-extraction` — Bloquea hasta que terminen todas las tareas

## Monitorear el progreso

### Ver estados de transcripción

```bash
docker exec backend python manage.py shell
>>> from apps.transcription.models import Transcription
>>> for t in Transcription.objects.all():
...     print(f"{t.recording.patient_reference}: {t.status}")
```

### Ver estados de extracción

```bash
>>> from apps.transcription.models import ExtractedRecord
>>> for r in ExtractedRecord.objects.all():
...     print(f"{r.transcription.recording.patient_reference}: {r.status} - {r.error or '✓'}")
```

### Ver datos extraídos

```bash
>>> r = ExtractedRecord.objects.filter(status='done').first()
>>> import json
>>> print(json.dumps(r.data, indent=2, ensure_ascii=False))
```

### Ver logs del worker

```bash
docker logs multiplayer-medico-worker-1 -f
```

Busca líneas como:
- `[tasks.transcribe_recording]` — Transcripción en progreso
- `[tasks.extract_record_information]` — Extracción en progreso
- `Extracción falló para record` — Errores de extracción

## Flujo de testing completo

```bash
# 1. Preparar ambiente
just local down
just local up

# 2. Aplicar cambios
docker exec backend python manage.py migrate transcription
docker exec backend python manage.py load_clinical_templates

# 3. Generar audios de ejemplo
docker exec backend python manage.py generate_sample_audios

# 4. Cargar audios y procesar
docker exec backend python manage.py load_sample_audios --wait-extraction

# 5. Verificar resultados
docker exec backend python manage.py shell -c "
from apps.transcription.models import ExtractedRecord
for r in ExtractedRecord.objects.select_related('transcription__recording', 'template'):
    print(f'{r.transcription.recording.patient_reference}: {r.status}')
    if r.status == 'done':
        print(f'  Template: {r.template.slug}')
        print(f'  Campos: {list(r.data.keys()) if r.data else []}')
"
```

## Esperado

Después de ejecutar `load_sample_audios --wait-extraction`, deberías ver:

```
✓ Ejemplo medico - Box 7: done
  Template: medico_uci
  Campos: ['metadatos', 'antecedentes', 'motivo_consulta', ...]
✓ Ejemplo enfermeria - Box 7: done
  Template: enfermeria_uci
  Campos: ['metadatos', 'signos_vitales', 'evaluacion_neurologica', ...]
...
```

## Integración con la API

### 1. Crear recording (igual que antes)

```bash
curl -X POST http://localhost:8000/api/recordings/ \
  -H "Authorization: Bearer TOKEN" \
  -F "audio=@audio.wav" \
  -F "source=in_app"
```

Esto automáticamente:
1. ✓ Crea `Recording`
2. ✓ Crea `Transcription` (pending)
3. ✓ Encola tarea de transcripción

### 2. Crear ExtractedRecord (nuevo)

Después de que termine la transcripción, encolar extracción:

```python
from apps.transcription.extraction_services import request_extraction

recording = Recording.objects.get(id=recording_id)
record = request_extraction(recording, template_slug="medico_uci")
```

Esto automáticamente:
1. ✓ Crea `ExtractedRecord` (pending) si la transcripción está lista
2. ✓ Encola tarea de extracción con Qwen

### 3. Leer resultados

```python
extracted = recording.transcription.extracted_record
if extracted.status == 'done':
    print(extracted.data)  # JSON estructurado
elif extracted.status == 'failed':
    print(extracted.error)
```

## Troubleshooting

### Extracción falla: "Invalid JSON in response"

**Problema:** Qwen devuelve respuesta que no es JSON válido.

**Soluciones:**
1. Revisar el prompt en `extraction_services.py` - puede ser demasiado específico
2. Aumentar `max_new_tokens` en `registry.py`
3. Usar modelo más grande: cambiar a `qwen-hf` si hay `HF_TOKEN`

### Validación falla contra schema

**Problema:** JSON de Qwen no cumple el schema del template.

**Debug:**
```python
from apps.clinical_templates import services
issues = services.validate_record(template, extracted_data)
for issue in issues:
    print(f"{issue.path}: {issue.message}")
```

**Soluciones:**
1. Revisar instrucciones del template en `data/medico_uci.json` → `x-plantilla.instrucciones_llm`
2. Validar que el schema está bien formado
3. Ver ejemplo en `data/ejemplos/medico_uci.json`

### Transcripción lenta (> 1 minuto)

**Esperado:** Primera ejecución carga modelo (~30-60s), subsecuentes < 10s.

**Verificar:**
```bash
docker logs multiplayer-medico-worker-1 | grep "loaded in"
```

### Proceso no aparece en Celery

**Verificar worker:**
```bash
docker exec backend python -c "
from celery import current_app
app = current_app
print('Tasks:', list(app.tasks.keys())[:5])
"
```

Debe incluir:
- `transcription.tasks.transcribe_recording`
- `transcription.tasks.extract_record_information`

## Archivos nuevos/modificados

```
backend/
├── apps/transcription/
│   ├── models.py                          ← ExtractedRecord
│   ├── extraction_services.py             ← Lógica de extracción
│   ├── tasks.py                           ← Tarea Celery (extract_record_information)
│   ├── management/commands/
│   │   ├── generate_sample_audios.py      ← Genera WAV en español
│   │   └── load_sample_audios.py          ← Carga audios a la BD
│   └── migrations/
│       └── 0002_extractedrecord.py        ← Migración
├── pyproject.toml                         ← pyttsx3
└── apps/clinical_templates/
    └── (sin cambios - reutiliza templates existentes)
```

## Próximos pasos

1. ✓ Extracción funcional con Qwen
2. → Integración en API REST (endpoint para enqueuer extracción)
3. → Dashboard para ver resultados
4. → Validaciones de negocio post-extracción
5. → Re-trying automático de fallos
