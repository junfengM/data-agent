BACKEND_PORT ?= 8787
FRONTEND_PORT ?= 5173
PYTHON ?= python3

.PHONY: backend frontend

backend:
	cd server && $(PYTHON) -m uvicorn app.main:app --reload --port $(BACKEND_PORT)

frontend:
	cd apps/web && npm run dev -- --port $(FRONTEND_PORT)

