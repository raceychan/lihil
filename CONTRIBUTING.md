# Contributing

No contribution is trivial and every contribution is appreciated, but we do have different focus and goals on different statge of this project

## RoadMap

### v0.1.x: Feature Cath

This stage currently focus on

- Feature catch: functional-wise, we should at least offer what fastapi has right now, given both fastapi and lihil uses starlette, this won't take too much effort.

- Test Coverage: we should maintain a test coverage > 99% every version onwards, for core components that already reached 100%, we should keep adding more test cases to it. the last patch of v0.1.x should have 100% test coverage.

- Correctness: we should stright out what is allowed-not allowed in `lihil`, also document that.

### v0.2.x Cool Stuff

we should implement those cool stuff we planned, including

- Out-of-process event system (RabbitMQ, Kafka, etc.).
- A highly performant schema-based query builder based on asyncpg
- Local command handler(http rpc) and remote command handler (gRPC)
- More middleware and official plugins (e.g., throttling, caching, auth).

### v0.3.x Performance Boost & Benchmarks & Comparison

- optimize our toolchains, including server, form parser, etc.

we might use low-level language heavily on this stage, such as c & cython,
if we do, keep them in a separate package so that It does not slow down our CI, since they require compilation.


### v0.4.x onwards: Implement-Feature-Request & Prepare for production

before 0.4.x, feature-requests might be accepted but won't be implemented, unless it is significant enhancement to our implementation.

Bug-fixes, typo-fixes, documentaions and tests are always welcome.



## Pre-commit hooks

We use `pre-commit` to enforce code style and catch common issues before commits.

Before making changes, install the hooks with:
```bash
pre-commit install
```

To run pre-commit hooks manually, use:

```bash
pre-commit run --all-files
```
