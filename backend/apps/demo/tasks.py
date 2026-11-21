"""Demo background tasks shipped with the base setup.

Each task showcases one of the tracker scenarios documented in
``lib/tracker/README.md``. Their docstrings are surfaced as descriptions
on the demo site's Celery Tracker page (via ``GET /tracker/celery-tasks``),
so each one explains what it demonstrates.
"""

import time

import tracker
from conf.celery import app


@app.task(bind=True, name="demo.tasks.sample_task")
def sample_task(self, steps: int = 3, step_duration: float = 1.0):
    """The minimal tracker demo: N uniform steps recorded with tracker.step().
    Watch the steps appear one by one while the task runs — no argument
    plumbing needed, the step picks the tracker up from the stamped header.
    """
    for i in range(steps):
        with tracker.step(f"Step {i + 1}"):
            time.sleep(step_duration)
    return {"steps_completed": steps}


@app.task(name="demo.tasks.import_batch")
def import_batch():
    """A multi-phase pipeline with named steps: Download → Validate → Load.
    Each phase is a tracker.step(), so the UI shows exactly which phase is
    running and how long each one took.
    """
    with tracker.step("Download"):
        time.sleep(1.2)
    with tracker.step("Validate"):
        time.sleep(0.8)
    with tracker.step("Load"):
        time.sleep(1.5)
    return {"rows_loaded": 1248}


@app.task(name="demo.tasks.doomed_import")
def doomed_import():
    """The same pipeline, but it fails on purpose at the Validate step.
    The step captures the exception and turns FAILURE, Load never runs, and
    the whole tracker reports failed — while Celery's own retry/failure
    handling stays untouched.
    """
    with tracker.step("Download"):
        time.sleep(1.2)
    with tracker.step("Validate"):
        time.sleep(0.8)
        raise ValueError("Batch contains 3 malformed rows")
    with tracker.step("Load"):  # pragma: no cover — never reached
        time.sleep(1.5)


@app.task(name="demo.tasks.long_haul")
def long_haul(stages: int = 10, stage_duration: float = 6.0):
    """A deliberately slow job (~1 minute) so you can cancel it mid-flight.
    Because the tracker knows every member task, the Cancel button revokes
    them all in one call.
    """
    for i in range(stages):
        with tracker.step(f"Stage {i + 1} of {stages}"):
            time.sleep(stage_duration)
    return {"stages_completed": stages}


@app.task(name="demo.tasks.index_section")
def index_section(section_id: int = 0):
    """One unit of the fan-out: indexes a single section. Part of the
    'Rebuild search index' scenario, which dispatches several of these in a
    chord — you can also run one alone.
    """
    with tracker.step(f"Index section {section_id}"):
        time.sleep(1.0 + (section_id % 3))
    return {"section_id": section_id, "documents": 100 + section_id * 17}


@app.task(name="demo.tasks.merge_indexes")
def merge_indexes(results: list | None = None):
    """The fan-in of the 'Rebuild search index' scenario: Celery dispatches
    it when every index_section finishes, and the propagated tracker stamp
    makes it join the same tracker automatically.
    """
    with tracker.step("Merge section indexes"):
        time.sleep(1.0)
    documents = sum(r["documents"] for r in results or [])
    return {"sections_merged": len(results or []), "documents": documents}
