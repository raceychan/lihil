.PHONY: run
run:
	uv run uvicorn docs.demos.app:lhl --interface asgi3 --http httptools --no-access-log --log-level "warning"

.PHONY: demo
demo:
	uv run uvicorn demo.main:lhl --interface asgi3 --http httptools --no-access-log --log-level "warning" --reload --factory

.PHONY: fast
fast:
	uv run uvicorn docs.demos.fast:app

.PHONY: example
example:
	uv run uvicorn docs.demos.auth_example:lhl --interface asgi3 --http httptools --no-access-log --log-level "warning" --reload

.PHONY: test
test:
	uv run python -m pytest -vx --capture=sys tests/

.PHONY: cov
cov:
	uv run python -m pytest --capture=sys tests/ --cov=lihil --cov-report term-missing

.PHONY: debug
debug:
	uv run python -m pytest -m debug tests/

# ====== dev========

.PHONY: docs
docs:
	uv run mkdocs serve

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


# ================ CI =======================

VERSION ?= x.x.x
BRANCH = version/$(VERSION)

# Command definitions
UV_CMD = uv run
HATCH_VERSION_CMD = $(UV_CMD) hatch version
CURRENT_VERSION = $(shell $(HATCH_VERSION_CMD))

# Main release target
.PHONY: release check-branch check-version update-version git-commit git-merge git-tag git-push build pypi-release delete-branch new-branch

release: check-branch check-version update-version git-commit git-merge git-tag git-push build

# Version checking and updating
check-branch:
	@if [ "$$(git rev-parse --abbrev-ref HEAD)" != "$(BRANCH)" ]; then \
		echo "Current branch is not $(BRANCH). Switching to it..."; \
		git switch -c $(BRANCH); \
		echo "Switched to $(BRANCH)"; \
	fi

check-version:
	@if [ "$(CURRENT_VERSION)" = "" ]; then \
		echo "Error: Unable to retrieve current version."; \
		exit 1; \
	fi
	$(call check_version_order,$(CURRENT_VERSION),$(VERSION))

update-version:
	@echo "Updating Pixi version to $(VERSION)..."
	@$(HATCH_VERSION_CMD) $(VERSION)

# Git operations
git-commit:
	@echo "Committing changes..."
	@git add -A
	@git commit -m "Release version $(VERSION)"

git-merge:
	@echo "Merging $(BRANCH) into master..."
	@git checkout master
	@git merge "$(BRANCH)"

git-tag:
	@echo "Tagging the release..."
	@git tag -a "v$(VERSION)" -m "Release version $(VERSION)"

git-push:
	@echo "Pushing to remote repository..."
	@git push origin master
	@git push origin "v$(VERSION)"

# Build and publish operations
build:
	@echo "Building version $(VERSION)..."
	@uv build

pypi-release:
	@echo "Publishing to PyPI with skip-existing flag..."
	@twine upload dist/*
	@git branch -d $(BRANCH)
	@git push origin --delete $(BRANCH)

# Branch management
delete-branch:
	@git branch -d $(BRANCH)
	@git push origin --delete $(BRANCH)

new-branch:
	@echo "Creating new version branch..."
	@if [ "$(CURRENT_VERSION)" = "" ]; then \
		echo "Error: Unable to retrieve current version."; \
		exit 1; \
	fi
	$(call increment_patch_version,$(CURRENT_VERSION))
	@echo "Creating branch version/$(NEW_VERSION)"
	@git checkout -b "version/$(NEW_VERSION)"
