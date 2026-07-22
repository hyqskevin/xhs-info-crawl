.PHONY: init migrate create-admin backup dev-api dev-worker dev-beat dev-web test test-e2e test-opencli test-poster test-poster-e2e test-poster-render build

init:
	./scripts/init.sh
migrate:
	cd backend && uv run alembic upgrade head
create-admin:
	./scripts/create-admin.sh
backup:
	./scripts/backup.sh

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

test-poster:
	uv run --project backend pytest backend/tests/test_poster_models.py backend/tests/test_poster_template_api.py backend/tests/test_poster_task_api.py -v
	npm --prefix frontend test -- --run src/views/PostersListView.spec.ts src/views/PosterWizardView.spec.ts

test-poster-e2e:
	npm --prefix frontend run test:e2e -- poster-flow.spec.ts

test-poster-render:
	bash tests/scripts/test_poster_real_render.sh

build:
	npm --prefix frontend run build
