.PHONY: fast
fast:
	uv run uvicorn fast_server:app --no-access-log --log-level "warning"

.PHONY: uvi
uvi:
	python3 -m uvicorn --interface asgi3 --no-access-log --log-level "warning" --http httptools uvicorn_server:app

.PHONY: aio
aio:
	python3 asyncio_server.py

.PHONY: star
star:
	python3 -m uvicorn --interface asgi3 --no-access-log --log-level "warning" --http httptools star_server:app


.PHONY: star2
star2:
	python3 -m granian --interface asgi star_server:app --http 1 --log-level "warning"

.PHONY: req
req:
	curl --header "Content-Type: application/json" \
	--request POST \
	--data '{"id": 1, "name":"user", "email":"user@email.com"}' \
	http://localhost:8000/fast/u
