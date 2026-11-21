# uncouple

Typed, structured configuration from environment variables. A thin layer
over [`python-decouple`](https://pypi.org/project/python-decouple/) and
[`pydantic`](https://docs.pydantic.dev/): declare a class with type
annotations, call `load()`, and get a validated, fully-typed config
object — with nesting, prefixes, custom field types, and a guard rail for
insecure development defaults.

`lib/` is on the Python path, so import it as a top-level package:

```python
from uncouple import Config, InsecureDefault, StringList
```

## Quickstart

Subclass `Config`, annotate fields, and `load()` with a prefix:

```python
from uncouple import Config, InsecureDefault, StringList


class DjangoConfig(Config):
    DEBUG: bool = False
    SECRET_KEY: str = InsecureDefault("insecure-development-key")
    ALLOWED_HOSTS: StringList = ["*"]
    DATABASE_URL: str = "sqlite:///db.sqlite3"


config = DjangoConfig.load(prefix="DJANGO")

config.DEBUG          # bool, cast from e.g. DJANGO_DEBUG=true
config.ALLOWED_HOSTS  # ["api.example.com", "www.example.com"] from a CSV value
```

Each field is read from `<PREFIX>_<FIELD>` (`DJANGO_SECRET_KEY`,
`DJANGO_DEBUG`, …) — from the process environment or a `.env` file, courtesy
of decouple — then parsed and validated by pydantic. Unset fields fall back
to their declared defaults.

`InsecureDefault` marks a dev-only fallback: it works locally with a
warning, and with `UNCOUPLE_REQUIRE_SECURE=1` set (production, CI) an unset
value becomes a hard failure at startup instead.

In this template, `conf/settings.py` is the canonical example: it declares
`DjangoConfig`, `EmailConfig`, `CeleryConfig` and `ProjectConfig`, loads each
with its own prefix, and uses `InsecureDefault` for `SECRET_KEY`.

## Reference

### Concepts

| Concept                  | What it is                                                              |
| ------------------------ | ----------------------------------------------------------------------- |
| `Config`                 | A pydantic `BaseModel` subclass whose annotations map to env vars.      |
| `Config.load(prefix=…)`  | Resolve every field from the environment, validate, and instantiate.    |
| `InsecureDefault(value)` | A dev-only fallback that warns when used — and can be made fatal.       |
| Field types              | `StringList`, `Addr`, `YarlUrl`, `ReadYaml`, `ConfigTable`, …           |

### Field resolution order

For each field, `load()` picks the first value that exists:

1. An environment variable / `.env` entry named `<PREFIX>_<FIELD>`
   (e.g. `DJANGO_SECRET_KEY`).
2. An explicit keyword passed to `load(**defaults)`.
3. The default declared on the class.
4. If none of the above, the field is omitted and pydantic applies its
   own default (or raises if the field is required).

Because resolution flows through pydantic, standard pydantic machinery —
`field_validator`, computed defaults, strict types — works as usual:

```python
from pydantic import field_validator


class DjangoConfig(Config):
    URL_PREFIX: str = "-"

    @field_validator("URL_PREFIX")
    @staticmethod
    def strip_slashes(val: str) -> str:
        return val.strip("/")
```

### Prefixes and nesting

A `prefix` namespaces every variable, letting several config objects share
one environment without collisions:

```python
django_config = DjangoConfig.load(prefix="DJANGO")   # DJANGO_*
email_config = EmailConfig.load(prefix="EMAIL")      # EMAIL_*
celery_config = CeleryConfig.load(prefix="CELERY")   # CELERY_*
```

Nesting composes prefixes automatically: a nested `Config` field reads from
`<PARENT_PREFIX>_<FIELD>_<NESTED_FIELD>`:

```python
class Database(Config):
    HOST: str = "localhost"
    PORT: int = 5432


class AppConfig(Config):
    database: Database = Database()


cfg = AppConfig.load(prefix="APP")
# database.HOST  ← APP_database_HOST
# database.PORT  ← APP_database_PORT
```

### Insecure defaults

`InsecureDefault` marks a fallback that is fine for local development but
must never silently reach production — secret keys, signing salts, demo
credentials:

```python
class DjangoConfig(Config):
    SECRET_KEY: str = InsecureDefault("insecure-development-key")
```

Behaviour depends on whether the environment supplies a real value:

| Situation                                            | Result                                                        |
| ---------------------------------------------------- | ------------------------------------------------------------- |
| Env var set                                          | The real value is used, no warning.                           |
| Env var unset                                        | Fallback used; `InsecureDefaultWarning` emitted, naming the key. |
| Env var unset **and** `UNCOUPLE_REQUIRE_SECURE` truthy | `load()` raises `InsecureConfigError` listing every offending key. |

Set `UNCOUPLE_REQUIRE_SECURE=1` in production (or CI) to turn "I forgot to
set a secret" from a quiet warning into a hard failure at startup.

### Field types

These annotated types add parsing on top of plain pydantic fields:

| Type                          | Accepts                          | Produces                              |
| ----------------------------- | -------------------------------- | ------------------------------------- |
| `StringList`                  | `"a,b,c"` or `["a", "b"]`        | `list[str]` (`["a", "b", "c"]`)       |
| `Addr`                        | `"host:port"`                    | `AddrStruct(host, port)`              |
| `YarlUrl`                     | a URL string                     | a `yarl.URL`                          |
| `ToYarlUrl`                   | validator to add to your own type | converts a parsed URL to `yarl.URL`  |
| `ReadYaml[T]`                 | a path to a YAML file            | `LoadedData[T]` (parsed + source path) |
| `ConfigTable(Cls, prefix=…)`  | a dict of named sub-configs      | `dict[str, Cls]`                      |

```python
from uncouple import Config, Addr, StringList, YarlUrl


class ServiceConfig(Config):
    LISTEN: Addr = "0.0.0.0:8000"        # → AddrStruct(host="0.0.0.0", port=8000)
    HOSTS: StringList = ["localhost"]    # CSV-friendly list
    UPSTREAM: YarlUrl = "https://api.example.com"  # → yarl.URL
```

`ConfigTable` builds a mapping of repeated config blocks, prefixing each
sub-config with its key — useful for per-tenant or per-queue settings:

```python
from uncouple import Config, ConfigTable


class Queue(Config):
    URL: str
    CONCURRENCY: int = 1


class AppConfig(Config):
    queues: ConfigTable(Queue, prefix="QUEUE") = {}
```

### Inspecting the environment

`Config.find()` iterates every available config key, combining `os.environ`
with decouple's loaded repository (`.env` file). Handy for debugging which
values are visible at load time.

### Where to look in this template

- `conf/settings.py` — real-world usage with multiple prefixed configs.
- `tests/test_uncouple.py` — the `InsecureDefault` behaviour exercised in
  isolation.
