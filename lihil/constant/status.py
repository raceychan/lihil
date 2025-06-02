from http import HTTPStatus
from typing import Any, Literal, get_args

from typing_extensions import TypeAliasType, TypeGuard

CONTINUE = Literal[100]
"""#### This interim response indicates that the client should continue the request or ignore the response if the request is already finished."""

SWITCHING_PROTOCOLS = Literal[101]
"""This response indicates that the server is switching protocols as requested by the client."""

PROCESSING = Literal[102]
"""#### Indicates that the server has received and is processing the request, but no response is available yet."""

EARLY_HINTS = Literal[103]
"""#### Used to return some response headers before the final HTTP message."""

OK = Literal[200]
"""#### The request has succeeded."""

CREATED = Literal[201]
"""#### The request has succeeded, and a new resource has been created as a result."""

ACCEPTED = Literal[202]
"""#### The request has been received but not yet acted upon."""

NON_AUTHORITATIVE_INFORMATION = Literal[203]
"""#### The request was successful, but the returned meta-information is not from the origin server."""

NO_CONTENT = Literal[204]
"""#### The server successfully processed the request and is not returning any content."""
RESET_CONTENT = Literal[205]
"""#### The server successfully processed the request, but instructs the client to reset the document view."""
PARTIAL_CONTENT = Literal[206]
"""#### The server is delivering only part of the resource due to a range header sent by the client."""
MULTI_STATUS = Literal[207]
"""#### Provides status for multiple independent operations."""
ALREADY_REPORTED = Literal[208]
"""#### The members of a DAV binding have already been enumerated in a previous part of the response."""
IM_USED = Literal[226]
"""#### The server has fulfilled a request for the resource, and the response is a representation of the result of one or more instance-manipulations applied to the current instance."""
MULTIPLE_CHOICES = Literal[300]
"""#### Indicates multiple options for the resource from which the client may choose."""
MOVED_PERMANENTLY = Literal[301]
"""#### This response code means that the requested resource has been permanently moved to a new URL."""
FOUND = Literal[302]
"""#### The requested resource has been temporarily moved to a different URI."""
SEE_OTHER = Literal[303]
"""#### The response to the request can be found under a different URI using a GET method."""
NOT_MODIFIED = Literal[304]
"""#### Indicates that the resource has not been modified since the last request."""
USE_PROXY = Literal[305]
"""#### The requested resource must be accessed through the proxy given by the `Location` field."""
RESERVED = Literal[306]
"""#### This response code is no longer used and reserved for future use."""
TEMPORARY_REDIRECT = Literal[307]
"""#### The requested resource is temporarily available at a different URI, and the client should use the same method for the request."""
PERMANENT_REDIRECT = Literal[308]
"""#### The requested resource is permanently available at a different URI, and the client should use the same method for future requests."""
BAD_REQUEST = Literal[400]
"""#### The server cannot process the request due to client error (e.g., malformed request syntax)."""
UNAUTHORIZED = Literal[401]
"""#### Authentication is required and has failed or has not yet been provided."""
PAYMENT_REQUIRED = Literal[402]
"""#### Reserved for future use; initially intended for digital payment systems."""
FORBIDDEN = Literal[403]
"""#### The client does not have access rights to the content."""
NOT_FOUND = Literal[404]
"""#### The server cannot find the requested resource."""
METHOD_NOT_ALLOWED = Literal[405]
"""#### The request method is known by the server but is not supported for the target resource."""
NOT_ACCEPTABLE = Literal[406]
"""#### The requested resource is only capable of generating content not acceptable according to the Accept headers sent in the request."""
PROXY_AUTHENTICATION_REQUIRED = Literal[407]
"""#### The client must first authenticate with the proxy."""
REQUEST_TIMEOUT = Literal[408]
"""#### The server timed out waiting for the request."""
CONFLICT = Literal[409]
"""#### Indicates a conflict with the current state of the resource."""
GONE = Literal[410]
"""#### Indicates that the resource is no longer available and will not be available again."""
LENGTH_REQUIRED = Literal[411]
"""#### The request did not specify the length of its content, which is required by the resource."""
PRECONDITION_FAILED = Literal[412]
"""#### The server does not meet one of the preconditions specified by the client."""
REQUEST_ENTITY_TOO_LARGE = Literal[413]
"""#### The request entity is larger than the server is willing or able to process."""
REQUEST_URI_TOO_LONG = Literal[414]
"""#### The URI provided was too long for the server to process."""
UNSUPPORTED_MEDIA_TYPE = Literal[415]
"""#### The request entity has a media that the server or resource does not support."""
REQUESTED_RANGE_NOT_SATISFIABLE = Literal[416]
"""#### The client has asked for a portion of the file, but the server cannot supply that portion."""
EXPECTATION_FAILED = Literal[417]
"""#### The server cannot meet the requirements of the Expect request-header field."""
IM_A_TEAPOT = Literal[418]
"""#### A humorous response indicating that the server refuses to brew coffee because it is a teapot."""
MISDIRECTED_REQUEST = Literal[421]
"""#### The request was directed at a server that is not able to produce a response."""
UNPROCESSABLE_ENTITY = Literal[422]
"""#### The request was well-formed but could not be processed due to semantic errors."""
LOCKED = Literal[423]
"""#### The resource that is being accessed is locked."""
FAILED_DEPENDENCY = Literal[424]
"""#### The request failed due to failure of a previous request."""
TOO_EARLY = Literal[425]
"""#### Indicates that the server is unwilling to risk processing a request that might be replayed."""
UPGRADE_REQUIRED = Literal[426]
"""#### The client should switch to a different protocol as indicated in the `Upgrade` header field."""
PRECONDITION_REQUIRED = Literal[428]
"""#### The server requires the request to be conditional to prevent conflicts."""
TOO_MANY_REQUESTS = Literal[429]
"""#### The user has sent too many requests in a given amount of time (rate limiting)."""
REQUEST_HEADER_FIELDS_TOO_LARGE = Literal[431]
"""#### The server refuses to process the request because its header fields are too large."""
UNAVAILABLE_FOR_LEGAL_REASONS = Literal[451]
"""#### The client has requested a resource that is unavailable due to legal reasons, such as censorship or government-mandated blocking."""
INTERNAL_SERVER_ERROR = Literal[500]
"""#### A generic error message indicating that the server encountered an unexpected condition that prevented it from fulfilling the request."""
NOT_IMPLEMENTED = Literal[501]
"""#### The server does not recognize the request method or lacks the ability to fulfill it."""
BAD_GATEWAY = Literal[502]
"""#### The server received an invalid response from the upstream server while acting as a gateway or proxy."""
SERVICE_UNAVAILABLE = Literal[503]
"""#### The server is currently unavailable due to overload or maintenance."""
GATEWAY_TIMEOUT = Literal[504]
"""#### The gateway or proxy server did not receive a timely response from the upstream server."""
HTTP_VERSION_NOT_SUPPORTED = Literal[505]
"""#### The HTTP version used in the request is not supported by the server."""
VARIANT_ALSO_NEGOTIATES = Literal[506]
"""#### The server has an internal configuration error: during content negotiation, the chosen variant is configured to engage in content negotiation itself, which results in circular references when creating responses."""
INSUFFICIENT_STORAGE = Literal[507]
"""#### The method could not be performed on the resource because the server is unable to store the representation needed to successfully complete the request."""
LOOP_DETECTED = Literal[508]
"""#### The server detected an infinite loop while processing the request."""
NOT_EXTENDED = Literal[510]
"""#### The client request declares an HTTP Extension (RFC 2774) that should be used to process the request, but the extension is not supported."""
NETWORK_AUTHENTICATION_REQUIRED = Literal[511]
"""#### Indicates that the client needs to authenticate to gain network access."""

Status = Literal[
    CONTINUE,
    SWITCHING_PROTOCOLS,
    PROCESSING,
    EARLY_HINTS,
    OK,
    CREATED,
    ACCEPTED,
    NON_AUTHORITATIVE_INFORMATION,
    NO_CONTENT,
    RESET_CONTENT,
    PARTIAL_CONTENT,
    MULTI_STATUS,
    ALREADY_REPORTED,
    IM_USED,
    MULTIPLE_CHOICES,
    MOVED_PERMANENTLY,
    FOUND,
    SEE_OTHER,
    NOT_MODIFIED,
    USE_PROXY,
    RESERVED,
    TEMPORARY_REDIRECT,
    PERMANENT_REDIRECT,
    BAD_REQUEST,
    UNAUTHORIZED,
    PAYMENT_REQUIRED,
    FORBIDDEN,
    NOT_FOUND,
    METHOD_NOT_ALLOWED,
    NOT_ACCEPTABLE,
    PROXY_AUTHENTICATION_REQUIRED,
    REQUEST_TIMEOUT,
    CONFLICT,
    GONE,
    LENGTH_REQUIRED,
    PRECONDITION_FAILED,
    REQUEST_ENTITY_TOO_LARGE,
    REQUEST_URI_TOO_LONG,
    UNSUPPORTED_MEDIA_TYPE,
    REQUESTED_RANGE_NOT_SATISFIABLE,
    EXPECTATION_FAILED,
    IM_A_TEAPOT,
    MISDIRECTED_REQUEST,
    UNPROCESSABLE_ENTITY,
    LOCKED,
    FAILED_DEPENDENCY,
    TOO_EARLY,
    UPGRADE_REQUIRED,
    PRECONDITION_REQUIRED,
    TOO_MANY_REQUESTS,
    REQUEST_HEADER_FIELDS_TOO_LARGE,
    UNAVAILABLE_FOR_LEGAL_REASONS,
    INTERNAL_SERVER_ERROR,
    NOT_IMPLEMENTED,
    BAD_GATEWAY,
    SERVICE_UNAVAILABLE,
    GATEWAY_TIMEOUT,
    HTTP_VERSION_NOT_SUPPORTED,
    VARIANT_ALSO_NEGOTIATES,
    INSUFFICIENT_STORAGE,
    LOOP_DETECTED,
    NOT_EXTENDED,
    NETWORK_AUTHENTICATION_REQUIRED,
]
""" ### HTTP status code (https://www.iana.org/assignments/http-status-codes/http-status-codes.xhtml)"""


def is_status(status: Any) -> TypeGuard[TypeAliasType]:
    if not (args := get_args(status)):
        return False
    return args[0] in Status.__args__


STATUS_CODE: dict[TypeAliasType, Status] = {
    CONTINUE: 100,
    SWITCHING_PROTOCOLS: 101,
    PROCESSING: 102,
    EARLY_HINTS: 103,
    OK: 200,
    CREATED: 201,
    ACCEPTED: 202,
    NON_AUTHORITATIVE_INFORMATION: 203,
    NO_CONTENT: 204,
    RESET_CONTENT: 205,
    PARTIAL_CONTENT: 206,
    MULTI_STATUS: 207,
    ALREADY_REPORTED: 208,
    IM_USED: 226,
    MULTIPLE_CHOICES: 300,
    MOVED_PERMANENTLY: 301,
    FOUND: 302,
    SEE_OTHER: 303,
    NOT_MODIFIED: 304,
    USE_PROXY: 305,
    RESERVED: 306,
    TEMPORARY_REDIRECT: 307,
    PERMANENT_REDIRECT: 308,
    BAD_REQUEST: 400,
    UNAUTHORIZED: 401,
    PAYMENT_REQUIRED: 402,
    FORBIDDEN: 403,
    NOT_FOUND: 404,
    METHOD_NOT_ALLOWED: 405,
    NOT_ACCEPTABLE: 406,
    PROXY_AUTHENTICATION_REQUIRED: 407,
    REQUEST_TIMEOUT: 408,
    CONFLICT: 409,
    GONE: 410,
    LENGTH_REQUIRED: 411,
    PRECONDITION_FAILED: 412,
    REQUEST_ENTITY_TOO_LARGE: 413,
    REQUEST_URI_TOO_LONG: 414,
    UNSUPPORTED_MEDIA_TYPE: 415,
    REQUESTED_RANGE_NOT_SATISFIABLE: 416,
    EXPECTATION_FAILED: 417,
    IM_A_TEAPOT: 418,
    MISDIRECTED_REQUEST: 421,
    UNPROCESSABLE_ENTITY: 422,
    LOCKED: 423,
    FAILED_DEPENDENCY: 424,
    TOO_EARLY: 425,
    UPGRADE_REQUIRED: 426,
    PRECONDITION_REQUIRED: 428,
    TOO_MANY_REQUESTS: 429,
    REQUEST_HEADER_FIELDS_TOO_LARGE: 431,
    UNAVAILABLE_FOR_LEGAL_REASONS: 451,
    INTERNAL_SERVER_ERROR: 500,
    NOT_IMPLEMENTED: 501,
    BAD_GATEWAY: 502,
    SERVICE_UNAVAILABLE: 503,
    GATEWAY_TIMEOUT: 504,
    HTTP_VERSION_NOT_SUPPORTED: 505,
    VARIANT_ALSO_NEGOTIATES: 506,
    INSUFFICIENT_STORAGE: 507,
    LOOP_DETECTED: 508,
    NOT_EXTENDED: 510,
    NETWORK_AUTHENTICATION_REQUIRED: 511,
}  # type: ignore


def phrase(status: int) -> str:
    return HTTPStatus(status).phrase


def code(status: TypeAliasType) -> Status:
    return STATUS_CODE[status]
