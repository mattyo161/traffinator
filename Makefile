.PHONY: up down build test test-backend test-frontend test-backend-watch seed-demo dump-cache logs

up: ## Build and start the full stack at http://localhost:8900
	docker compose up -d --build

down: ## Stop the stack (add -v manually to also wipe the DB)
	docker compose down

build:
	docker compose build

test: test-backend test-frontend ## Run the entire test suite

test-backend: ## Django tests against a real Postgres (earthdistance included)
	docker compose run --rm backend python manage.py test commute -v 2

test-frontend: ## Vitest unit tests inside the node build stage
	docker compose run --rm frontend-test

seed-demo: ## Load the demo commute fixture so the UI works with zero API calls
	docker compose exec backend python manage.py load_cache fixtures/demo_commute.csv

dump-cache: ## Export the current cache to stdout as CSV (redirect to a file)
	docker compose exec backend python manage.py dump_cache

logs:
	docker compose logs -f backend
