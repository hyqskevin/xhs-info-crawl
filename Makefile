.PHONY: init dev-api dev-worker dev-beat dev-web test test-e2e test-opencli build

init:
	./scripts/init.sh

dev-api:
	./scripts/dev-api.sh

dev-worker:
	./scripts/dev-worker.sh

dev-beat:
	./scripts/dev-beat.sh

dev-web:
	./scripts/dev-web.sh

test:
	uv run --project backend pytest backend/tests -q
	npm --prefix frontend test -- --run

test-e2e:
	npm --prefix frontend run test:e2e

test-opencli:
	./scripts/test-opencli.sh

build:
	npm --prefix frontend run build
