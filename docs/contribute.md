# Contribute

No contribution is trivial and every contribution is appreciated, however, we do have different focus & goals in different stage of this project

## RoadMap


### version 0.1.x: Feature Parity

- Feature Parity: we should offer core functionalities of a web framework ASAP, similar to what fastapi is offering right now. Given both fastapi and lihil uses starlette, this should not take too much effort.

- Correctness: We should have a preliminary understanding of lihil's capabilities—knowing what should be supported and what shouldn't. This allows us to distinguish between correct and incorrect usage by users.

- Test Coverage: There's no such thing as too many tests. For every patch, we should maintain at least 99% test coverage, and 100% for the last patch of 0.1.x. For core code, 100% coverage is just the baseline—we should continuously add test cases to ensure reliability.

Based on the above points, in version v0.1.x, we welcome contributions in the following areas:

- Documentation: Fix and expand the documentation. Since lihil is actively evolving, features may change or extend, and we need to keep the documentation up to date.

- Testing: Contribute both successful and failing test cases to improve coverage and reliability.

- Feature Requests: We are open to discussions on what features lihil should have or how existing features can be improved. However, at this stage, we take a conservative approach to adding new features unless there is a significant advantage.


### version 0.2.x Cool Stuff

- Out-of-process event system (RabbitMQ, Kafka, etc.).
- A highly performant schema-based query builder based on asyncpg
- Local command handler(http rpc) and remote command handler (gRPC)
- More middleware and official plugins (e.g., throttling, caching, auth).


### version 0.3.x Performance boost



### version 0.4.x onwards

- implementing requested feature, fix bugs, be as production-ready as possible.


## Pre-commit hooks

We use `pre-commit` to enforce code style and catch common issues with formmatting before commits.

Before making changes, install the hooks with:
```bash
pre-commit install
```

To run pre-commit hooks manually, use:
```bash
pre-commit run --all-files
```
