.PHONY: run
run:
	uv run uvicorn app:lhl --interface asgi3 --http httptools --no-access-log --log-level "warning"

.PHONY: dev
dev:
	uv run app.py

.PHONY: fast
fast:
	uv run fast.py

.PHONY: test
test:
	uv run pytest tests/

.PHONY: debug
debug:
	uv run pytest -m debug tests/
# ==========

.PHONY: profile
profile:
	uv run pyinstrument -r html -o profiling/lihil_$$(date +%Y%m%d_%H%M%S).html app.py

.PHONY: profile_fast
profile_fast:
	uv run pyinstrument -r html -o profiling/fast_$$(date +%Y%m%d_%H%M%S).html fast.py

.PHONY: spy
spy:
	uv run py-spy top -- python app.py

