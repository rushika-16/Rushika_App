# AI Credit Card Assistant

Streamlit + FastAPI demo that provides credit card pre-qualification with:
- chat-based onboarding,
- SSN-based credit score lookup (stubbed API),
- policy-grounded explanation flow,
- safety guardrails,
- SSN masking in UI and DB logs.

## Project Structure

```
credit-card-ai-demo/
├── backend/
│   ├── main.py
│   ├── service.py
│   ├── eligibility.py
│   ├── rag.py
│   └── ...
├── frontend/
│   └── app.py
├── requirements.txt
├── render.yaml
├── uat_check.py
└── DEMO_RUNBOOK.md
```

## Prerequisites

- Python 3.9+
- `pip`

## Local Setup

From project root:

```bash
cd /Users/rushika/Documents/Code/credit-card-ai-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Locally

Backend (terminal 1):

```bash
cd /Users/rushika/Documents/Code/credit-card-ai-demo
source .venv/bin/activate
PYTHONPATH=/Users/rushika/Documents/Code/credit-card-ai-demo \
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Frontend (terminal 2):

```bash
cd /Users/rushika/Documents/Code/credit-card-ai-demo
source .venv/bin/activate
python -m streamlit run /Users/rushika/Documents/Code/credit-card-ai-demo/frontend/app.py \
  --server.port 8501 --server.address 127.0.0.1
```

Open:
- Frontend: http://127.0.0.1:8501
- Backend docs: http://127.0.0.1:8000/docs

## SSN Lookup + Masking Behavior

- User enters SSN in either `XXX-XX-XXXX` or `9 digits` format.
- UI provides an eye toggle to show/hide SSN while typing.
- Lookup endpoint: `POST /lookup-credit-score` with JSON body:

```json
{ "ssn": "123-45-6789" }
```

- Response includes masked SSN only (last 3 digits visible), e.g. `***-**-789`.
- Raw SSN is not shown in chat and is not persisted in decision log snapshot.

## Dummy SSN Mapping (Stub)

| SSN | Score |
|---|---:|
| 123-45-6789 | 850 |
| 987-65-4321 | 825 |
| 111-22-3333 | 810 |
| 222-33-4444 | 780 |
| 555-66-7777 | 745 |
| 999-00-1111 | 590 |
| 888-77-6666 | 550 |
| 444-55-6666 | 520 |
| 333-22-1111 | 680 |
| 000-12-3456 | 350 |

Fallback for unknown SSN: `600`.

## Run UAT

```bash
cd /Users/rushika/Documents/Code/credit-card-ai-demo
source .venv/bin/activate
python uat_check.py
```

## Deploy on Render (One-Click)

This repo includes `render.yaml` with two services:
- `credit-card-ai-backend`
- `credit-card-ai-frontend`

Steps:
1. Push code to GitHub.
2. In Render, create a Blueprint from this repository.
3. Render reads `render.yaml` and provisions both services.

Notes:
- Frontend receives backend URL via `BACKEND_URL` from backend service URL.
- Backend uses persistent disk path for SQLite via `DATABASE_URL=sqlite:////var/data/credit_card.db`.
