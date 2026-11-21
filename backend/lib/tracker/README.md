# tracker

Progress tracking for **Celery** workloads. Wrap a dispatch in a context
manager and every task it publishes is stamped with a shared tracker ID,
registered as a member of that tracker, and made queryable — with live
Celery state merged in — through a small service and a Django Ninja API.

It answers a question Celery itself does not: *"these N tasks belong to
one logical job — what's the overall state, and which named steps has it
gone through?"*

`lib/` is on the Python path, so import it as a top-level package:

```python
import tracker
from tracker import track, step, state, configure
```

## Quickstart

Wrap a dispatch in `track()` — everything published inside the block shares
one tracker ID:

```python
import tracker

with tracker.track("Nightly ETL") as t:
    extract.delay()
    transform.delay()
    load.delay()

t.tracker_id  # UUID covering all three tasks as one job
```

Inside a task, record named phases with `step()` — it picks the tracker up
from the stamped header Celery propagates, no argument plumbing required:

```python
@app.task
def extract():
    with tracker.step("Fetch data"):
        fetch()
    with tracker.step("Stage rows"):
        stage()
```

Read back the merged state (persisted records + live Celery results) at any
time:

```python
st = tracker.state(t.tracker_id)

st.state               # PENDING / STARTED / SUCCESS / FAILURE
st.progress_completed  # member tasks in a terminal state
st.progress_target     # total member tasks
st.steps               # the named phases recorded via step()
```

In this template the default backend is Redis (via Celery's
`result_backend`), so this works out of the box — no configuration needed.

### How it fits together

```
with track("Nightly ETL") as t:        # 1. persist a TrackerState, open a stamping scope
    extract.delay()                    # 2. before_task_publish stamps each message with t.tracker_id
    transform.delay()                  #    and registers the task id as a member
    load.delay()
                                       # 3. on the worker, tracker.step(...) records named phases
                                       #    against the stamp Celery propagated
state(t.tracker_id)                    # 4. read back merged state (persisted + live AsyncResult)
```

Members are discovered passively: a `before_task_publish` signal handler
inspects every outgoing message and, if it carries the `tracker_id` stamp,
records the task ID as a member. This fires on the client **and** on workers
(chain/chord callbacks carry the propagated stamp), so the member set is
built incrementally with no canvas introspection.

## Scenarios

All of these are runnable on the demo site's **Tracker** page — the demo
tasks in `apps/demo/tasks.py` implement them one to one.

### An endpoint that starts a job the frontend can watch

The most common shape: a view wraps the dispatch in `track()` and returns
the `tracker_id`; the frontend polls the tracker API for progress.

```python
# apps/reports/api.py
import tracker
from ninja import Router
from apps.reports.tasks import build_report

router = Router()


@router.post("/reports/{report_id}/build")
def build(request, report_id: int):
    with tracker.track(f"Report {report_id}") as t:
        build_report.delay(report_id)
    return {"tracker_id": t.tracker_id}
```

The client then polls `GET /tracker/tracked-tasks/{tracker_id}`, which
returns status, `progress_completed` / `progress_target`, and every step
recorded so far — the template's React `TaskProgressCard` /
`TaskTrackerProgress` components consume exactly this. For tasks that need
no custom endpoint, `POST /tracker/celery-tasks/{task_name}/run` does the
same thing generically (see [HTTP API](#http-api)).

### Fan-out / fan-in with Celery canvas

Stamps propagate through canvas primitives, so a chord's callback —
dispatched later, from a worker — joins the same tracker automatically:

```python
from celery import chord

with tracker.track("Rebuild search index") as t:
    chord(
        (index_section.s(section_id) for section_id in section_ids),
        merge_indexes.s(),
    ).delay()
```

Every `index_section` task is registered as a member at publish time. When
the group finishes and Celery dispatches `merge_indexes`, the propagated
stamp registers it too — `progress_target` grows from N to N + 1 as the job
runs, with no canvas introspection. The same applies to `chain` and `group`.

### A multi-phase pipeline that can fail halfway

Steps give a job a narrative the UI can show — including where it died:

```python
@app.task
def import_batch(batch_id: int):
    with tracker.step("Download"):
        source_path = download(batch_id)
    with tracker.step("Validate"):
        validate(source_path)   # raises on bad data
    with tracker.step("Load"):
        load(source_path)
```

If `validate()` raises, the *Validate* step is marked `FAILURE` with the
exception captured in its `info`, the *Load* step is never recorded, and the
exception propagates unchanged — Celery retry/failure handling is untouched.
The tracker aggregate turns `FAILURE`, and `state(...).steps` shows
*Download* succeeded and *Validate* did not.

### Cancelling a running job

Every member is known, so one call revokes the whole job — useful for a
"Cancel" button next to a progress bar:

```python
from tracker.service import TrackerService

result = TrackerService().revoke_tracked_tasks(tracker_id)
result.revoked_task_ids  # every member that was revoked
```

Over HTTP the same operation is `POST /tracker/tracked-tasks/{tracker_id}/cancel`
(the template's `TaskControlButton` wires this up).

## Reference

### Concepts

| Concept               | What it is                                                                 |
| --------------------- | -------------------------------------------------------------------------- |
| `track(title)`        | Context manager that stamps every task published inside it.                |
| `step(title)`         | Context manager / decorator marking a named phase *inside* a running task. |
| `state(id)`           | Load a merged `TrackerState` (persisted + live Celery) by tracker or task. |
| `TrackerState`        | The aggregate view: status, progress, member tasks and steps.              |
| `ExecutionState`      | One unit of execution — a member task or a step.                           |
| `TrackerBackend`      | Pluggable persistence (Redis or Django ORM).                               |
| `configure(backend)`  | Set the process-wide default backend explicitly.                           |

### `track(title)`

- Persists the `TrackerState` on `__enter__` (before any task is dispatched)
  so member registration always finds the row.
- Yields a `TrackingContext` whose `tracker_id` covers everything published
  in the block — single tasks, groups, chains, chords alike.
- Dispatch stays plain `.delay()` / `.apply_async()`; `track` only stamps and
  observes.

### `step(title)`

- As a context manager, marks a named phase inside a task body; as a
  decorator, wraps the whole body as one step.
- On exit the step is marked `SUCCESS`, or `FAILURE` (capturing the
  exception) if the block raised — exceptions are never suppressed.
- Outside a Celery task, or on a task with no tracker stamp, it logs a
  warning and becomes a no-op — always safe to leave in place.

### `state(id)` and aggregation

`state()` (backed by `TrackerService.get_tracker`) loads the persisted
record, then merges live Celery state for every member via `AsyncResult`.
It accepts either a tracker ID or one of its member Celery task IDs — the
service maps a task ID back to its tracker.

Fields on the returned `TrackerState`:

| Field                 | Meaning                                                    |
| --------------------- | ---------------------------------------------------------- |
| `state`               | Aggregate state (reduction rules below).                   |
| `progress_completed`  | Member tasks in a terminal state.                          |
| `progress_target`     | Total member tasks.                                        |
| `tasks`               | `{celery_task_id: ExecutionState}`.                        |
| `steps`               | `[ExecutionState]` recorded via `tracker.step()`.          |
| `started_on`          | Derived from the earliest step / creation time.            |
| `completed_on`        | Set once the aggregate reaches a terminal state.           |

Per-task states reduce to one aggregate:

- any `FAILURE` → `FAILURE`
- any `STARTED`/`RETRY` → `STARTED`
- any `REVOKED` (rest terminal) → `REVOKED` (cancelled)
- all `SUCCESS` → `SUCCESS`
- otherwise → `PENDING`

### Backends

Persistence is pluggable through the `TrackerBackend` ABC.
`configure(backend)` sets a process-wide default; call it once at startup
(e.g. in an `AppConfig.ready()`).

**Redis (default, zero-config).** If you never call `configure()`, the
backend is auto-resolved from the Celery app: an explicit `tracker_backend`
on the app config wins, otherwise a `RedisTrackerBackend` is built from
`result_backend` when it points at `redis://` / `rediss://`. State, members,
steps, and a task→tracker reverse index live under `celery-tracker:*` keys.

**Django ORM.** `DjangoTrackerBackend` persists trackers and steps as model
rows. The model classes are injected so the library stays decoupled from any
particular schema:

```python
import tracker
from myapp.models import TrackedTask, TrackedTaskStep

tracker.configure(
    tracker.DjangoTrackerBackend(
        task_model=TrackedTask,
        step_model=TrackedTaskStep,
    )
)
```

**Writing your own.** Subclass `TrackerBackend` and implement `save` /
`load` / `list_all`, `add_member` / `get_members`, and `add_step` /
`update_step` / `get_steps`. `add_member` must be safe to call concurrently
from the client and multiple workers. Optionally override
`find_tracker_id_for_member` to support lookup by member task ID.

### HTTP API

`tracker.api` exposes a Django Ninja `router`. In this template it is
mounted at `/tracker` (see `conf/urls.py`):

| Method & path                               | Purpose                                  |
| ------------------------------------------- | ---------------------------------------- |
| `GET /tracked-tasks`                        | List all trackers (live state merged).   |
| `GET /tracked-tasks/{tracker_id}`           | Tracker detail with tasks and steps.     |
| `GET /tracked-tasks/by-celery-id/{id}`      | Same detail, keyed by member task ID.    |
| `POST /tracked-tasks/{tracker_id}/cancel`   | Revoke the tracker's Celery tasks.       |
| `GET /celery-tasks`                         | List registered Celery task types.       |
| `POST /celery-tasks/{task_name}/run`        | Dispatch a task by name, tracked.        |

`POST /celery-tasks/{task_name}/run` wraps the dispatch in `track()` and
returns the new `tracker_id`, so a frontend can immediately poll
`/tracked-tasks/{tracker_id}` for progress.

> Endpoints under `/tracked-tasks/{id}/children` and `/tracked-tasks/stats/*`
> are present for interface compatibility but return `501 Not Implemented`.

### Testing

Configure an in-memory or fake backend explicitly with
`tracker.configure(...)` so tests don't depend on a live Redis or Celery
app. Because `step` no-ops outside a task context, task bodies can be
called directly without a worker.

### What this is not

- **Not** a Celery result backend — it sits *alongside* one and reads
  live state from it via `AsyncResult`.
- **Not** a scheduler or queue — dispatch is still plain `.delay()` /
  `.apply_async()`; `track` only stamps and observes.
- **Not** event sourcing — there is no event log; state is a snapshot
  merged from persisted records and live Celery results.
