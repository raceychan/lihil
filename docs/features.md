# Feature

## Param Parsing & Validation

Lihil provides a sophisticated parameter parsing system that automatically extracts and converts parameters from different request locations:

- Multiple Parameter Sources: Automatically parse parameters from query strings, path parameters, headers, and request bodies
- Type-Based Parsing: Parameters are automatically converted to their annotated types
- Alias Support: Define custom parameter names that differ from function argument names
- Custom Decoders: Apply custom decoders to transform raw input into complex types

```python

@Route("/users/{user_id}")
async def create_user(
    user_id: str,                                           # from URL path
    name: Query[str],                                       # from query string
    auth_token: Header[str, Literal["x-auth-token"]],       # from request headers
    user_data: UserPayload                                  # from request body
):
    # All parameters are automatically parsed and type-converted
    ...
```

## Dependency Injection

Lihil features a powerful dependency injection system:

- Automatic Resolution: Dependencies are automatically resolved and injected based on type hints.
- Scoped Dependencies: Support for nested, infinite levels of scoped, singleton, and transient dependencies
- Nested Dependencies: Dependencies can have their own dependencies
- Factory Support: Create dependencies using factory functions with custom configuration
- Lazy Initialization: Dependencies are only created when needed

```python
async def get_conn(engine: Engine):
    async with engine.connect() as conn:
        yield conn

async def get_users(conn: AsyncConnection):
    return await conn.execute(text("SELECT * FROM users"))

@Route("users").get
async def list_users(users: Annotated[list[User], use(get_users)], is_active: bool=True):
    return [u for u in users if u.is_active == is_active]
```

for more in-depth tutorials on DI, checkout https://lihil.cc/ididi

## OpenAPI schemas

Lihil automatically generates comprehensive OpenAPI documentation:

- Type-Based Schema Generation: Schemas are derived from Python type annotations
- Detailed Parameter Documentation: Documents all parameters with their sources, types, and requirements
- Response Documentation: Automatically documents response types and status codes
- Error Documentation: Includes detailed error schemas in the documentation
- Examples Support: Add examples to make your API documentation more helpful

## Exception-Problem Mapping & Problem Page

Lihil implements the RFC 7807 Problem Details standard for error reporting

lihil maps your expcetion to a `Problem` and genrate detailed response based on your exception.

```python
class OutOfStockError(HTTPException[str]):
    "The order can't be placed because items are out of stock"
    __status__ = 422

    def __init__(self, order: Order):
        detail: str = f"{order} can't be placed, because {order.items} is short in quantity"
        super().__init__(detail)
```

when such exception is raised from endpoint, client would receive a response like this

```json
{
    "type_": "out-of-stock-error",
    "status": 422,
    "title": "The order can't be placed because items are out of stock",
    "detail": "order(id=43, items=[massager], quantity=0) can't be placed, because [massager] is short in quantity",
    "instance": "/users/ben/orders/43"
}
```

## Message System

publish command/event anywhere in your app with both in-process and out-of-process event handlers. Optimized data structure for maximum efficiency, de/serialize millions events from external service within seconds.

## typing support

typing plays a significant role in the world of `lihil`, lihil combines generics, function overriding, paramspec and other advanced typing features to give you the best typing support possible.

with its dedicated, insanely detailed typing support, lihil will give you something to smile about.

![typing](./images/good_typing_status.png)

![typing2](./images/good_typing2.png)
