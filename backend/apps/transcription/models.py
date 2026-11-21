from django.db import models


class Audio(models.Model):
    """Audio cargado. `data` se vacía en cuanto su transcripción queda guardada."""

    name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    data = models.BinaryField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name


class Transcription(models.Model):
    audio = models.OneToOneField(Audio, on_delete=models.CASCADE, related_name="transcription")
    text = models.TextField()
    language = models.CharField(max_length=20)
    model_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Transcripción de {self.audio.name}"
