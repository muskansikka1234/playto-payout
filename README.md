# Playto Payout Engine

A production-grade payout engine built for the Playto Pay Founding Engineer Challenge.

Handles merchant balance tracking, payout requests with idempotency, concurrent fund holds via database-level locking, and async bank settlement simulation via Celery.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Django 4.2 + Django REST Framework |
| Database | PostgreSQL 15 (BigIntegerField for paise, SELECT FOR UPDATE for concurrency) |
| Background Jobs | Celery + Redis |
| Beat Scheduler | django-celery-beat |
| Frontend | React 18 + Tailwind CSS |
| Deployment | Docker Compose / Railway / Render |

---

## Quick Start (Docker — recommended)

```bash
git clone <your-repo-url>
cd playto-payout

docker-compose up --build
```

That's it. On first boot:
- PostgreSQL and Redis start
- Django runs migrations
- Seed script populates 3 merchants with credit history
- Celery worker + beat scheduler start
- React frontend is served at http://localhost:3000
- Django API at http://localhost:8000/api/v1/

---

## Manual Setup (without Docker)

### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Node.js 20+

### Backend

```bash
cd backend

# Create virtualenv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your DB credentials

# Run migrations
python manage.py migrate

# Seed merchants
python manage.py seed

# Set up Celery Beat schedule
python manage.py setup_beat

# Start Django
python manage.py runserver
```

### Celery (in separate terminals)

```bash
# Worker
celery -A payout_engine worker -l info

# Beat scheduler
celery -A payout_engine beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### Frontend

```bash
cd frontend
npm install
npm start
# Opens at http://localhost:3000
```

---

## Environment Variables

```env
SECRET_KEY=your-secret-key
DEBUG=True
DB_NAME=playto_payout
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
REDIS_URL=redis://localhost:6379/0
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

---

## API Reference

### Merchants

```
GET  /api/v1/merchants/                     List all merchants with balances
GET  /api/v1/merchants/{id}/                Merchant detail + bank accounts
GET  /api/v1/merchants/{id}/ledger/         Full ledger with balance breakdown
```

### Payouts

```
POST /api/v1/payouts/                       Create payout (idempotent)
GET  /api/v1/payouts/list/                  List merchant payouts
GET  /api/v1/payouts/{id}/                  Payout detail + status
```

### Required Headers for Payout Create

```
X-Idempotency-Key: <uuid4>    Merchant-supplied UUID. Same key = same response.
X-Merchant-ID: <uuid4>        Merchant identifier (would be JWT sub in production).
```

### Example: Create Payout

```bash
curl -X POST http://localhost:8000/api/v1/payouts/ \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -H "X-Merchant-ID: <merchant-uuid>" \
  -d '{"amount_paise": 50000, "bank_account_id": "<bank-account-uuid>"}'
```

---

## Running Tests

```bash
cd backend
python manage.py test api.tests --verbosity=2
```

Tests cover:
- **Concurrency**: Two simultaneous 60₹ payouts on ₹100 balance → exactly one succeeds
- **Idempotency**: Same UUID key twice → identical response, no duplicate payout
- **State machine**: Illegal transitions (completed→pending, failed→completed) raise ValueError
- **Ledger integrity**: Balance always equals sum of all ledger entries

---

## Architecture Decisions

### Why BigIntegerField for amounts?

Floating point arithmetic is catastrophically wrong for money. `0.1 + 0.2 = 0.30000000000000004` in IEEE 754. Storing paise as integers means exact arithmetic — no rounding errors ever.

### Why SELECT FOR UPDATE?

Python-level checks like "if balance >= amount: deduct" are a race condition. Thread A reads 100₹, Thread B reads 100₹, both see sufficient balance, both deduct 60₹ — overdraft. `SELECT FOR UPDATE` acquires a DB-level exclusive row lock on the merchant row, forcing Thread B to wait until Thread A commits. Thread B then re-reads the now-reduced balance.

### Why ledger entries instead of a balance column?

A balance column requires read-modify-write on every operation, with locking on that column. A ledger is append-only: credits are positive, debits are negative. Balance = `SUM(amount_paise)`. This is naturally atomic, gives full audit history, and lets us verify integrity at any time.

### Why HOLD entries?

When a payout is requested, we immediately place a negative HOLD entry. This means the available balance (`SUM(all entries)` minus `SUM(HOLD entries)`) drops instantly, preventing double-spend before the payout settles. On success, HOLD converts to DEBIT. On failure, a matching HOLD_RELEASE reverses it.

---

## Seeded Test Data

After running `python manage.py seed`, you get:

| Merchant | Balance | Email |
|---|---|---|
| Arjun Singh | ₹4,750.00 | arjun@example.com |
| Priya Sharma | ₹14,000.00 | priya@example.com |
| Rahul Tech Solutions | ₹14,000.00 | rahul@example.com |

---

## Deployment (Render)

```bash
# Backend: add a render web service pointing to /backend
# Set env vars in render dashboard
# Add PostgreSQL and Redis plugins

# Frontend: deploy /frontend to render
# Set REACT_APP_API_URL=https://your-backend.render.app/api/v1
```
