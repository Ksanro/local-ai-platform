"""Request middleware for the gateway.

Provides two middleware classes: one for injecting unique request IDs
into response headers, and one for measuring request processing time.
"""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestMiddleware(BaseHTTPMiddleware):
    """Middleware that adds a unique request ID to response headers.

    Each incoming request receives a UUID4 request ID that is attached
    to the ``X-Request-ID`` response header for tracing purposes.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process request and add request ID header.

        Generates a UUID4, calls the next middleware/handler, then
        attaches the request ID to the response headers.

        Args:
            request: The incoming ASGI request.
            call_next: The next middleware or handler in the chain.

        Returns:
            The response with ``X-Request-ID`` header set.
        """
        # Use the client-supplied X-Request-ID when present;
        # otherwise generate one and store it in the ASGI scope so the
        # handler can read it for logging.
        request_id = request.headers.get("X-Request-ID")
        if request_id is None:
            request_id = str(uuid.uuid4())

        request.scope["request_id"] = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Middleware that measures and records request processing time.

    Records the wall-clock time between receiving the request and
    sending the response, then attaches it to the ``X-Process-Time``
    response header as a floating-point seconds value.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process request and measure timing.

        Records the start time before calling the next handler, then
        computes the elapsed time and attaches it to the response.

        Args:
            request: The incoming ASGI request.
            call_next: The next middleware or handler in the chain.

        Returns:
            The response with ``X-Process-Time`` header set.
        """
        start_time: float = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response
