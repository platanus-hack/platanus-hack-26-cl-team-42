# Quick Start: Extracción de Información con Qwen

## Setup Rápido (5 minutos)

### 1. Reconstruir Docker

```bash
just local down
just local up
```

### 2. Aplicar cambios

```bash
docker exec backend python manage.py migrate transcription
docker exec backend python manage.py load_clinical_templates
```

### 3. Generar y cargar audios de ejemplo

```bash
# Generar WAV en español
docker exec backend python manage.py generate_sample_audios

# Cargar y procesar (espera ~1-2 minutos)
docker exec backend python manage.py load_sample_audios --wait-extraction
```

## Verificar Resultados

```bash
# Ver transcripciones
docker exec backend python manage.py shell
>>> from apps.transcription.models import Transcription, ExtractedRecord
>>> Transcription.objects.values_list('recording__patient_reference', 'status')
<QuerySet [('Ejemplo medico - Box 7', 'done'), ('Ejemplo enfermeria - Box 7', 'done'), ...]>

# Ver extracción
>>> ExtractedRecord.objects.select_related('template').values_list('template__slug', 'status')
<QuerySet [('medico_uci', 'done'), ('enfermeria_uci', 'done'), ...]>

# Ver datos extraídos (ejemplo)
>>> import json
>>> r = ExtractedRecord.objects.filter(status='done').first()
>>> print(json.dumps(r.data, indent=2, ensure_ascii=False))
```

## Usar en Python

```python
from apps.transcription.extraction_services import request_extraction
from apps.recordings.models import Recording

# Después de cargar un audio y esperar a que se transcriba
recording = Recording.objects.get(id=...)

# Enqueuer extracción
extracted_record = request_extraction(recording, template_slug="medico_uci")

# Verificar estado (después de 5-10 segundos)
extracted_record.refresh_from_db()
if extracted_record.status == 'done':
    print(extracted_record.data)  # JSON estructurado
elif extracted_record.status == 'failed':
    print(f"Error: {extracted_record.error}")
```

## Monitorear Celery

```bash
# Ver logs en tiempo real
docker logs multiplayer-medico-worker-1 -f

# Buscar errores
docker logs multiplayer-medico-worker-1 | grep -i error
```

## Qué Cambió

| Componente | Cambio |
|-----------|--------|
| `Transcription` | Sin cambios (Whisper) |
| `ExtractedRecord` | ✨ Nuevo modelo |
| `extraction_services.py` | ✨ Nuevo servicio |
| `tasks.py` | ✨ Tarea `extract_record_information` |
| `pyproject.toml` | ✨ Agregó `pyttsx3` |
| Migrations | ✨ `0002_extractedrecord.py` |

## Troubleshooting

**Problema:** "ModuleNotFoundError: No module named 'pyttsx3'"

```bash
# Reconstruir Docker
just local down
just local up
```

**Problema:** "ClinicalTemplate matching query does not exist"

```bash
docker exec backend python manage.py load_clinical_templates
```

**Problema:** Extracción muy lenta (> 1 minuto)

Primera ejecución tarda 30-60s cargando Qwen. Las siguientes son rápidas.

## Next: Integración API

```python
# En recording/api.py, después de crear Recording:

from apps.transcription.extraction_services import request_extraction

@router.post("/recordings", response=RecordingOut)
def create_recording(request, payload: RecordingIn):
    recording = ...  # Crear recording
    
    # Enqueuer transcripción (ya existe)
    request_transcription(recording)
    
    # Enqueuer extracción (nuevo)
    if payload.template_slug:
        request_extraction(recording, payload.template_slug)
    
    return to_out(recording)
```
