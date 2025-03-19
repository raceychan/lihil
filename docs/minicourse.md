# Mini Course

we will go through some of the common concept related to web development that would help you better understand our tutorials.

## `Resource`

### Any identifiable entity that can be accessed via a URL

Don't overthink it—if you don’t like the term `resource`, think of it as an `object`.

## URI

### Uniform Resource Identifier

A string that uniquely identifies a resource. a uri can be a url, a urn, or both. a url follows the format:

> `protocol://domain/path?query#fragment`

`#fragment` is commonly used for client-side navigation, usually you do not need it writing server side application.

Example:

`https://myhost.com/users/lhl/orders?nums=3`

When you see a RESTful API with a URI like this, even without prior knowledge, you can infer that:

- It is a website hosted at `myhost.com`, using the `https` protocol.
- It is accessing a resource named `orders`, which belongs to a specific user `lhl`.
- It includes a query parameter, `nums`, with the value `3`.

`URL` (Uniform Resource Locator): A type of URI that not only identifies a resource but also provides a way to access it. URLs generally include a scheme (protocol), domain, path, query parameters, and optionally a fragment.
