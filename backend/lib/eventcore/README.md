# eventcore

A small framework for modelling **Commands** and **Events** formally in a
Django application.

It sits at a deliberate midpoint: richer than scattering business logic
across views and `save()` overrides, but **not** event sourcing. Models
stay the source of truth and are mutated in place — events are a shared
vocabulary for *state transitions* and the seam where *side effects* (Celery
tasks, notifications, cascading commands) attach.

`lib/` is on the Python path, so import it as a top-level package:

```python
import eventcore
from eventcore import Command, CommandError, Event, ModelEvent, apply_event, invoke, on
```

## Quickstart

Three pieces, three files. An **event** is a fact that can happen to a model
and knows how to apply itself:

```python
# orders/events.py
from eventcore import ModelEvent
from orders.models import Order

OrderEvent = ModelEvent[Order]


class ShipmentCreated(OrderEvent):
    carrier_name: str

    def apply(self, model: Order) -> None:
        model.shipments.create(carrier_name=self.carrier_name)
```

A **command** is a validated intention that orchestrates the change — it
loads state, enforces business rules, applies events, and saves:

```python
# orders/commands.py
from eventcore import Command, CommandError, apply_event
from orders.events import ShipmentCreated
from orders.models import Order


class ShipOrder(Command):
    order_id: int
    carrier_name: str

    class OrderNotFound(CommandError): ...

    def perform(self):
        try:
            order = Order.objects.get(pk=self.order_id)
        except Order.DoesNotExist:
            raise self.OrderNotFound("Order %s not found", self.order_id)

        apply_event(order, ShipmentCreated(carrier_name=self.carrier_name))
        order.save()
        return order
```

A **policy** reacts to an event with a side effect, wired in the app's
`ready()`:

```python
# orders/apps.py
import eventcore
from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = "apps.orders"

    def ready(self):
        from apps.notifications.tasks import SendShippingEmailTask
        from orders.events import ShipmentCreated

        eventcore.on(ShipmentCreated, lambda e: SendShippingEmailTask.delay(e.model.id))
```

Calling code — a view, a Celery task, the shell — only sees the command:

```python
order = eventcore.invoke(ShipOrder(order_id=42, carrier_name="ups"))
```

The command validates the intent (pydantic), `invoke` runs it in a
transaction, the event mutates the model and announces the fact, and policies
attach side effects after commit — without the command knowing about them:

```
invoke(command)   ──applies──▶  apply_event(model, SomeEvent(...))
                                      │
                                      ├─▶ event.apply(model)   # mutate state in place
                                      └─▶ emit(event)          # notify subscribers
                                              │
                                              └─▶ on(SomeEvent) handlers run (after commit)
```

## Reference

### Concepts

| Concept                   | What it is                                                        |
| ------------------------- | ----------------------------------------------------------------- |
| `Command`                 | A validated, named intention to change the system.                |
| `CommandError`            | An expected, domain-level failure raised from a command.          |
| `invoke(command)`         | Run a command in a transaction, then announce it to subscribers.  |
| `Event`                   | A fact: something that happened (a pydantic payload).             |
| `ModelEvent[M]`           | An event that knows how to `apply()` itself to a model of type M. |
| `apply_event(model, ev)`  | Apply an event to a model and announce it to subscribers.         |
| `on(Type, fn)`            | Subscribe `fn` to a command/event type (and its subclasses).      |

### Events

- Subclass `ModelEvent[M]` (typically via an alias like
  `OrderEvent = ModelEvent[Order]`), declare payload fields as pydantic
  annotations, and implement `apply(self, model)` to mutate the instance.
- Apply with the `apply_event(model, event)` free function — models are plain
  Django models, no base class or mixin.
- `apply_event` mutates the instance and defers subscriber dispatch to
  transaction commit. It does **not** call `save()` — the calling command
  decides when to persist (see [Convention, not
  enforcement](#convention-not-enforcement)).
- `apply_event` must run inside a command invocation; calling it outside
  `invoke()` raises (see [Occurrence metadata](#occurrence-metadata-meta)).

### Commands

- Subclass `Command`, declare payload fields as pydantic annotations, and
  implement `perform()`. Construction validates the payload.
- Declare expected failures as nested `CommandError` subclasses
  (`class OrderNotFound(CommandError): ...`) and raise them from `perform()`
  with a printf-style message.
- `invoke(command)` runs `perform()` inside `transaction.atomic()` — always —
  so every event applied within the command commits atomically and side
  effects fire only once the unit of work is durable. After commit, the
  command itself is emitted to `on(Command, ...)` subscribers (audit logs,
  metrics, …).
- Commands may not call `invoke()` from inside `perform()` — that raises
  `NestedCommandError`. To chain commands, use a policy (below).

### Policies

A **policy** is a rule that reacts to a domain event: when the event is
applied, the policy triggers follow-up actions (another command, a Celery
task, a notification) without the code that applied the event knowing about
it. By convention an app defines them in `policies.py`:

```python
# orders/policies.py
from orders.events import ShipmentCreated


def notify_customer(event: ShipmentCreated) -> None:
    from apps.notifications.tasks import SendShippingEmailTask

    SendShippingEmailTask.delay(event.model.id)
```

…and wires them in `apps.py` `ready()` with one `eventcore.on(...)` line per
policy, so `ready()` is the single place that shows what reacts to what.

- A policy registered for a base type also receives subclasses, so
  `on(ModelEvent, audit)` observes every model event.
- Policies are **the only sanctioned way to chain commands**: react to one of
  command A's events (or to A itself via `on(Command, ...)`) with a policy
  that invokes command B. Because policies run after A commits, B starts as
  its own top-level transition with its own correlation context.
- Commands flow through the same registry, so `on(Command, ...)` observes
  every invocation — handlers on commands are plain listeners; the term
  *policy* is reserved for event reactions.

### Occurrence metadata (meta)

`invoke()` establishes an `EventMeta` envelope for the run — `occurred_at`
(now), `actor` (unset for now), and a fresh `correlation_id` — and makes it
the active context (a `contextvars.ContextVar`) while `perform()` executes.
Every `apply_event` call inside the command binds the same envelope onto the
event, so:

- an event's `apply()` can read `self.meta.occurred_at` (and `actor` /
  `correlation_id`), and so can any subscriber via `event.meta`;
- the command and all of its events share one `correlation_id` — the
  `eventcore.app` log records it on every row, so a command and its effects
  can be traced together.

Because the envelope comes from the command context, events can only be
applied inside `invoke()` — this is deliberate: every state change is
attributable to a command. The envelope is captured onto the event at apply
time, so `on_commit` subscribers still see `event.meta` after the context has
unwound. (The context is per-thread and does not propagate into Celery tasks;
pass any `correlation_id` you need explicitly.)

### Dispatch timing and testing

Subscribers run **after the surrounding database transaction commits**
(`transaction.on_commit`), so side effects never fire for work that gets
rolled back. In autocommit (no active transaction) they run immediately.

In tests, run the deferred handlers within a (rolled-back) test transaction
using Django's on-commit capture — pytest-django exposes it as a fixture:

```python
with django_capture_on_commit_callbacks(execute=True):
    invoke(PlaceOrder(customer_name="Ada", item="Keyboard"))
# subscribers have now run
```

`Registry.run(message)` tests dispatch/matching directly and synchronously,
without a transaction. `eventcore.clear()` removes all registered subscribers
(useful for test isolation).

### Convention, not enforcement

`apply_event(model, event)` mutates the model and emits the event — and
nothing else. It does not override `save()`, intercept field assignment, or
block queryset `update()`; the full ORM keeps working. That cuts both ways:

- **Direct mutation bypasses subscribers.** `order.status = "shipped";
  order.save()` emits no event and nothing reacts. Fine for incidental
  bookkeeping (counters, denormalized caches, internal timestamps); wrong for
  any transition other parts of the system care about.
- **Persistence stays explicit.** Neither events nor `apply_event` ever call
  `save()`, so a command can apply several events to one or more models and
  persist once, keeping the whole transition atomic inside `invoke()`'s
  transaction.

Rule of thumb: if a change is a *domain fact* — a status change, a lifecycle
milestone, anything a team member would name in conversation — it deserves a
command and an event. If it is plumbing no one would ever subscribe to, the
plain ORM is the right tool.

### Introspection

Every `Command` and `Event` subclass registers itself when its module is
imported, so the running process can enumerate them:

```python
from eventcore import registered_commands, registered_events

registered_commands()  # -> [CancelOrder, PlaceOrder, ShipOrder, ...]
registered_events()    # -> [OrderCancelled, OrderPlaced, OrderShipped, ...]
```

This makes a live catalog (names, pydantic fields, docstrings) available to,
say, an API that documents the domain's commands and events.

### Live documentation graph

Installing ``eventcore.contrib.docs`` (already wired in this template) exposes:

- **UI:** ``/{URL_PREFIX}/eventcore-docs/`` (login required)
- **API:** ``/{URL_PREFIX}/api/eventcore/graph``

The graph is built at runtime from registered commands/events, AST of each
command's ``perform`` (``apply_event`` calls), and ``eventcore.on`` policies.
Editor deep-links (Cursor/VS Code) work when ``EVENTCORE_DOCS_HOST_ROOT`` is set
or when ``just local up`` writes ``.eventcore-docs-host-root`` for the Docker
bind mount.

### Optional logging app

The bundled `eventcore.app` Django app subscribes with `on(Command, …)` and
`on(Event, …)` and records a `LogRecord` row for every command invocation and
every applied event:

```python
# settings.py
INSTALLED_APPS += ["eventcore.app"]
```

It is entirely opt-in: `eventcore` itself never imports the app, and the core
machinery works whether or not it is installed.

### What this is not

- **Not** event sourcing — there is no event log and no rebuild-from-events.
- **Not** a message bus — dispatch is in-process; durable/async fan-out is
  the job of the subscribers (e.g. enqueue a Celery task).
- **Not** a persistence layer — events mutate models but never `save()`.
