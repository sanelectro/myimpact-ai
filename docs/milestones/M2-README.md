# MyImpact AI — M2 README

## Milestone 2 — Persistence & Data Layer

### Objective

M2 gives MyImpact AI a proper persistence layer so it can **store, retrieve, version, and manage employee impact data**.

The persistence foundation is built on:

```text
FastAPI
   ↓
Services
   ↓
Repositories
   ↓
SQLAlchemy
   ↓
PostgreSQL
```

M2 also establishes database schema versioning through Alembic.

---

## M2 Architecture

The intended data flow is:

```text
User
  ↓
Goal
  ↓
Evidence
  ↓
Evidence Version
  ↓
Evidence → Goal Mapping
  ↓
Impact Assessment
  ↓
Report
```

A key design principle is that evidence can change over time.

For example:

```text
Evidence V1
"Implemented deployment monitoring"

        ↓ source content changes

Evidence V2
"Implemented deployment monitoring including CPU,
memory and restart alerts"
```

The system can therefore preserve evidence history and support re-evaluation of impact when evidence changes.

---

# M2.1 — Domain Models

The following seven persistence/domain concepts were established:

1. `User`
2. `Goal`
3. `Evidence`
4. `EvidenceVersion`
5. `EvidenceMapping`
6. `ImpactAssessment`
7. `Report`

Corresponding database tables:

```text
users
goals
evidence
evidence_versions
evidence_mappings
impact_assessments
reports
```

---

# M2.2 — PostgreSQL Persistence Foundation

## M2.2.1 — PostgreSQL Configuration

PostgreSQL was selected as the relational persistence store.

Local development uses Docker with:

```text
Image:       postgres:16
Container:   pgtest
Host port:   5555
Container:   5432
Database:    myimpact
User:        myimpact
```

The application does **not** hardcode the database connection string.

Configuration is provided through `.env`:

```env
DATABASE_URL=postgresql+psycopg://myimpact:<local-password>@localhost:5555/myimpact
```

The `.env` file should not be committed to Git.

---

## M2.2.2 — PostgreSQL Connectivity

### Start local PostgreSQL

Example Docker command:

```bash
docker run --name pgtest   -e POSTGRES_USER=myimpact   -e POSTGRES_PASSWORD=<your-local-password>   -e POSTGRES_DB=myimpact   -p 5555:5432   -d postgres:16
```

Verify the container:

```bash
docker ps --filter "name=pgtest"
```

Verify PostgreSQL directly:

```bash
docker exec -it pgtest psql -U myimpact -d myimpact -c "SELECT 1;"
```

Expected result:

```text
?column?
----------
        1
(1 row)
```

---

## M2.2.3 — SQLAlchemy Connectivity

SQLAlchemy provides the application-to-PostgreSQL database layer.

The application database engine is created from the configured `DATABASE_URL`.

Connectivity was verified with:

```bash
python -c "from sqlalchemy import text; from app.db.session import engine; connection = engine.connect(); print(connection.execute(text('SELECT current_database()')).scalar()); connection.close()"
```

Expected result:

```text
myimpact
```

### Important local configuration note

The PostgreSQL container exposes:

```text
localhost:5555 → container:5432
```

Therefore the application connection must use:

```text
localhost:5555
```

and not:

```text
localhost:5432
```

The SQLAlchemy connectivity issue encountered during M2 was resolved by correcting this port.

---

## M2.2.4 — SQLAlchemy Model Registration

All database models are imported from:

```text
app/db/models/__init__.py
```

The registration module imports:

```python
from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.evidence_version import EvidenceVersionDB
from app.db.models.goal import GoalDB
from app.db.models.impact_assessment import ImpactAssessmentDB
from app.db.models.report import ReportDB
from app.db.models.user import UserDB
```

This ensures the model metadata is loaded into:

```python
Base.metadata
```

Verification:

```bash
python -c "from app.db.base import Base; import app.db.models; print(sorted(Base.metadata.tables.keys()))"
```

Expected tables:

```text
['evidence',
 'evidence_mappings',
 'evidence_versions',
 'goals',
 'impact_assessments',
 'reports',
 'users']
```

The seemingly unused:

```python
import app.db.models
```

is intentional. Importing the package loads all model modules so SQLAlchemy's metadata knows about the tables.

---

## M2.2.5 — Alembic Setup

Alembic is used for database schema version control.

Initialize Alembic:

```bash
alembic init alembic
```

This creates:

```text
alembic/
alembic.ini
```

Alembic was configured to use the application's database settings rather than hardcoding a connection string in `alembic.ini`.

Key configuration in `alembic/env.py`:

```python
from sqlalchemy import create_engine
from app.config.settings import get_settings
from app.db.base import Base
import app.db.models
```

Metadata:

```python
target_metadata = Base.metadata
```

Database engine:

```python
connectable = create_engine(
    get_settings().database_url,
    poolclass=pool.NullPool,
)
```

### Alembic check

The initial:

```bash
alembic check
```

successfully connected to PostgreSQL and detected the expected schema operations before the initial migration existed.

That was expected at this stage.

---

# M2.2.6 — Initial Database Migration

The initial migration was generated from the SQLAlchemy models:

```bash
alembic revision --autogenerate -m "create initial MyImpact schema"
```

Migration created:

```text
alembic/versions/df31ba4869d9_create_initial_myimpact_schema.py
```

Migration applied with:

```bash
alembic upgrade head
```

Result:

```text
Running upgrade  -> df31ba4869d9, create initial MyImpact schema
```

---

# M2.2.7 — Database Integration Verification

## Verify database tables

```bash
docker exec -it pgtest psql -U myimpact -d myimpact -c "\dt"
```

The database contains:

```text
alembic_version
evidence
evidence_mappings
evidence_versions
goals
impact_assessments
reports
users
```

## Verify Alembic version

```bash
docker exec -it pgtest psql -U myimpact -d myimpact -c "SELECT * FROM alembic_version;"
```

Expected migration revision:

```text
df31ba4869d9
```

## Verify through SQLAlchemy

```bash
python -c "from sqlalchemy import inspect; from app.db.session import engine; print(inspect(engine).get_table_names())"
```

Verified tables:

```text
['alembic_version',
 'users',
 'evidence',
 'goals',
 'reports',
 'evidence_mappings',
 'evidence_versions',
 'impact_assessments']
```

---

# M2.2.8 — Validation

Unit tests:

```bash
python -m pytest tests/unit -v
```

Final result:

```text
8 passed in 0.69s
```

During validation, one settings test exposed Python 3.11 Enum membership behavior.

The original assertion:

```python
assert settings.llm_provider in LLMProvider
```

was replaced with:

```python
assert settings.llm_provider in [provider.value for provider in LLMProvider]
```

After the fix:

```text
8 passed
```

---

# Current M2 Status

| Step | Status |
|---|---|
| M2.1 — Domain Models | ✅ Complete |
| M2.2.1 — PostgreSQL Configuration | ✅ Complete |
| M2.2.2 — Database Connectivity | ✅ Complete |
| M2.2.3 — SQLAlchemy Connectivity | ✅ Complete |
| M2.2.4 — SQLAlchemy Model Registration | ✅ Complete |
| M2.2.5 — Alembic Setup | ✅ Complete |
| M2.2.6 — Initial Database Migration | ✅ Complete |
| M2.2.7 — Database Integration Verification | ✅ Complete |
| M2.2.8 — Validation | ✅ Complete |

## M2.2 Result

The MyImpact AI application now has a working:

- PostgreSQL database
- SQLAlchemy engine/session foundation
- registered persistence models
- Alembic migration framework
- initial database schema
- live database verification
- passing unit-test baseline

---

# Important Files

Key M2 files/folders include:

```text
app/
├── config/
│   └── settings.py
│
└── db/
    ├── base.py
    ├── session.py
    └── models/
        ├── __init__.py
        ├── user.py
        ├── goal.py
        ├── evidence.py
        ├── evidence_version.py
        ├── evidence_mapping.py
        ├── impact_assessment.py
        └── report.py

alembic/
├── env.py
├── script.py.mako
└── versions/
    └── df31ba4869d9_create_initial_myimpact_schema.py

alembic.ini
.env
.env.example
requirements.txt
tests/
```

---

# Local Reproduction — M2 Database Foundation

Assuming Docker and the Python environment are already configured:

### 1. Start PostgreSQL

```bash
docker start pgtest
```

If the container does not exist, create it using the Docker command shown in M2.2.2.

### 2. Verify PostgreSQL

```bash
docker exec -it pgtest psql -U myimpact -d myimpact -c "SELECT 1;"
```

### 3. Verify application configuration

```bash
python -c "from app.config.settings import get_settings; print(get_settings().database_url)"
```

Make sure the configured URL points to:

```text
localhost:5555
```

### 4. Verify SQLAlchemy

```bash
python -c "from sqlalchemy import text; from app.db.session import engine; connection = engine.connect(); print(connection.execute(text('SELECT current_database()')).scalar()); connection.close()"
```

### 5. Apply migrations

```bash
alembic upgrade head
```

### 6. Run unit tests

```bash
python -m pytest tests/unit -v
```

---

# Design Notes

### Why SQLAlchemy?

SQLAlchemy provides the Python database abstraction used by the application while still allowing PostgreSQL-specific capabilities when needed.

### Why Alembic?

Alembic provides version-controlled database schema changes.

The intended lifecycle is:

```text
SQLAlchemy Model Change
        ↓
alembic revision --autogenerate
        ↓
Migration Review
        ↓
alembic upgrade head
        ↓
Updated PostgreSQL Schema
```

### Why version Evidence?

Evidence is not treated as static text.

If source evidence changes, MyImpact AI should be able to preserve the previous version and evaluate the new version independently. This supports trustworthy historical reports and future impact re-evaluation.

---

# Boundary of M2

M2 establishes the **persistence foundation**.

It does not yet implement the application repository/service behavior for CRUD and domain workflows.

The next milestone is:

## M2.3 — Repository Layer

Planned repositories:

```text
UserRepository
GoalRepository
EvidenceRepository
EvidenceVersionRepository
EvidenceMappingRepository
ImpactAssessmentRepository
ReportRepository
```

Target flow:

```text
FastAPI
   ↓
Service
   ↓
Repository
   ↓
SQLAlchemy
   ↓
PostgreSQL
```

M2.3 will build on the database foundation established here.

---

## Commit Readiness Checklist

- [x] PostgreSQL configured for local development
- [x] Docker PostgreSQL verified
- [x] SQLAlchemy connected to PostgreSQL
- [x] Seven persistence models registered
- [x] Alembic initialized
- [x] Alembic connected to application settings
- [x] Initial migration generated
- [x] Initial migration applied
- [x] Live database schema verified
- [x] Alembic version verified
- [x] Unit tests passing
- [x] M2.2 complete
- [ ] M2.3 Repository Layer — next

---

**Milestone status: M2.2 Complete — ready to proceed to M2.3 Repository Layer.**
