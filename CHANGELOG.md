# CHANGELOG

## version 0.1.1

This is the very first version of lihil, but we already have a working version that users can play alon..

### Features

- core functionalities to an ASGI webserver, routing, http methods, `GET`, `POST`, `PUT`, `DELTE`
- ASGI middleware support
- variosu response and encoding supoprt, json response, text response, stream response, etc.
- bulitin json serialization/deseriazation using `msgspec`
- `CustomEncoder` and `CustomDecoder` support
- Performant and powerful dependency injection using `ididi`
- Builtin message support, `EventBus` that enables user to publish events to multiple listenrs.
- auto generated openapi shemas and swagger web-ui documentation
- rfc-9457 problem details and problems web-ui documentation
- many other things, stay tune to our docs!

## version 0.1.2

### Improvements

- `InvalidRequestErrors` is now a sublcass of `HTTPException`

### Fix

- fix a bug where `problem.__name__` is used for search param instead of `problem.__problem_type__`
- no longer import our experimental server by default

## version 0.1.3

### Fix

- fix a bug where if lifespan is not provided, callstack won't be built
- remove `loguru.logger` as dependency.

### Improvements

- `static` now works with `uvicorn`


## version 0.1.4

### Fix

- a quick fix for not catching HttpException when sub-exception is a generic exception


## version 0.1.5

### Feature

- User can now alter app behavior by assigning a config file

```python
lhl = Lihil(config_file="pyproject.toml")
```
Note: currently only toml file is supported

or by inheriting `lihil.config.AppConfig` instance menually,

```python
lhl = Lihil(app_config=AppConfig(version="0.1.1"))
```

this is particularly useful if you want to inherit from AppConfig and extend it.

```python
from lihil.config import AppConfig

class MyConfig(AppConfig):
    app_name: str

config = MyConfig.from_file("myconfig.toml")
```

### improvements

- now user can directly import `Body` from lihil

```python
from lihil import Body
```

## version 0.1.6

### Feature

- user can now override configuration with cli arguments.

example:

```python
python app.py --oas.title "New Title" --is_prod true
```

would override `AppConfig.oas.title` and `AppConfig.is_prod`.

this comes handy when for overriding configs that are differernt according to the deployment environment.

- add a test helper `Route.has_listener` to check if a listener is registered.

- `LocalClient.call_route`, a test helper for testing routes.

### Fix

- fix a bug with request param type being GenericAliasType

we did not handle GenericAliasType case and treat it as `Annotated` with `flatten_annotated`.

and we think if a type have less than 2 arguments then it is not `Annotated`,
but thats not the case with GenericAlias

- fix a bug with request param type optional type

we used to check if a type is union type by checking

```python
isinstance(type, UnionType)
```

However, for type hint like this

```python
a: int | None
```

it will be interpreted as `Optional`, which is a derived type of `Union`

- fix a bug where `CustomerDecoder` won't be use
previously whenever we deal with `Annotated[Path[int], ...]`

we treat it as `Path[int]` and ignore its metadatas, where decoder will be placed, this is now fixed as we detect and perserve the decoder before discarding the matadata.

- fix a bug where `Route.listen` will fail silently when listener does not match condition, meaning it has not type hint of derived event class.

Example:

```python
async def listen_nothing(event):
    ...

Rotue.listen(listen_nothing) 
```

This would fail silently before this fix

- Fix a bug with `Lihil.static` where if content is instance of str, and content type is `text` it will still be encoded as json