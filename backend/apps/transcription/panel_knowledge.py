"""Base de conocimiento de cada profesional, construida con sus propios informes.

Por ahora se asume que ya existe: se arma al vuelo con los informes validados que el profesional
generó al usar la app (su «experiencia»). Es la única pieza que habría que reemplazar si la base
pasa a guardarse aparte. Los casos previos se anonimizan: el agente de un profesional no debe
revelar a los demás datos de otros pacientes.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from . import reconciliation_services
from .models import Report
from .report_assistant import _compact

MAX_CASES = 3
MAX_CASE_CHARS = 700
MIN_TERM_LENGTH = 4
REPORTS_CONSIDERED = 60
DRUG_SECTIONS = (
    ("medicamentos", "nombre"),
    ("drogas_infusion", "farmaco"),
    ("antimicrobianos", "farmaco"),
)


@dataclass(frozen=True)
class Knowledge:
    """Lo que sabe un profesional: un perfil de cómo trabaja y casos previos relevantes."""

    profile: str
    cases: list[str]


def knowledge_for(professional, question: str) -> Knowledge:
    """Perfil y casos previos del profesional más afines a la pregunta."""
    reports = list(
        Report.objects.filter(author=professional, status=Report.Status.DONE)
        .select_related("patient")
        .order_by("-created_at")[:REPORTS_CONSIDERED]
    )
    return Knowledge(profile=_profile(reports), cases=_relevant_cases(reports, question))


def knowledge_of_profile(profile) -> Knowledge:
    """Un miembro sin cuenta no tiene informes: vale la experiencia escrita en su perfil."""
    experience = profile.experience.strip() or (
        "Sin experiencia registrada: opina solo con el criterio general de su profesión."
    )
    return Knowledge(profile=experience, cases=[])


def _profile(reports: list[Report]) -> str:
    if not reports:
        return "Sin informes previos en la app: opina solo con el criterio general de su profesión."
    drugs: Counter[str] = Counter()
    for report in reports:
        for section, key in DRUG_SECTIONS:
            for item in (report.data or {}).get(section) or []:
                if isinstance(item, dict) and item.get(key):
                    drugs[str(item[key])] += 1
    line = f"Ha dejado {len(reports)} informes validados en la app."
    if drugs:
        line += (
            " Fármacos que más reporta: "
            + ", ".join(name for name, _ in drugs.most_common(5))
            + "."
        )
    return line


def _relevant_cases(reports: list[Report], question: str) -> list[str]:
    terms = _terms(question)
    scored = []
    for report in reports:
        text = _case_text(report)
        score = len(terms & _terms(text))
        if score:
            scored.append((score, report.created_at, text))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [text for _, _, text in scored[:MAX_CASES]]


def _case_text(report: Report) -> str:
    sections = []
    for key, value in (report.data or {}).items():
        compact = _compact(value)
        if compact:
            sections.append(f"{key}: {compact}")
    text = "; ".join(sections)[:MAX_CASE_CHARS]
    if report.patient is not None:
        text = reconciliation_services.anonymize(text, report.patient)
    return text


def _terms(text: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return {word for word in re.findall(r"[a-z0-9]+", folded) if len(word) >= MIN_TERM_LENGTH}
