from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

from app.enums import PayoutStatus, SaleStatus
from app.exceptions import ConflictError, NotFoundError, PayoutSystemError, ValidationError
from app.serializers import to_primitive
from app.services import PayoutSystem


RouteResult = Tuple[int, Dict[str, Any]]


class PayoutApiHandler(BaseHTTPRequestHandler):
    system = PayoutSystem()

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _dispatch(self, method: str) -> None:
        try:
            status_code, body = self._route(method)
        except NotFoundError as error:
            status_code, body = HTTPStatus.NOT_FOUND, {"error": str(error)}
        except (KeyError, ValueError) as error:
            status_code, body = HTTPStatus.BAD_REQUEST, {"error": f"Invalid request: {error}"}
        except (ValidationError, ConflictError) as error:
            status_code, body = HTTPStatus.BAD_REQUEST, {"error": str(error)}
        except PayoutSystemError as error:
            status_code, body = HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)}
        except Exception as error:  # pragma: no cover
            status_code, body = HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Unexpected error: {error}"}

        self._send_json(status_code, body)

    def _route(self, method: str) -> RouteResult:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if method == "GET" and path == "/":
            return HTTPStatus.OK, {
                "service": "User Payout Management System API",
                "status": "ok",
                "availableEndpoints": {
                    "GET /": "API overview",
                    "GET /health": "Health check",
                    "POST /sales": "Create a pending sale",
                    "POST /jobs/advance-payouts": "Run advance payout job",
                    "POST /sales/{sale_id}/reconcile": "Reconcile a sale to approved/rejected",
                    "POST /withdrawals": "Initiate a withdrawal",
                    "POST /withdrawals/{payout_id}/status": "Update withdrawal status",
                    "GET /users/{user_id}/wallet": "Get wallet, sales, payouts, and ledger summary",
                },
            }

        if method == "GET" and path == "/health":
            return HTTPStatus.OK, {"status": "ok"}

        if method == "POST" and path == "/sales":
            payload = self._read_json()
            sale = self.system.sale_service.create_sale(
                user_id=payload["userId"],
                brand=payload["brand"],
                earning=payload["earning"],
            )
            return HTTPStatus.CREATED, to_primitive(sale)

        if method == "POST" and path == "/jobs/advance-payouts":
            payouts = self.system.advance_service.run()
            return HTTPStatus.OK, {
                "processedCount": len(payouts),
                "payouts": to_primitive(payouts),
            }

        if method == "POST" and path.startswith("/sales/") and path.endswith("/reconcile"):
            sale_id = path.split("/")[2]
            payload = self._read_json()
            payout = self.system.reconciliation_service.reconcile(
                sale_id=sale_id,
                new_status=SaleStatus(payload["status"]),
            )
            return HTTPStatus.OK, to_primitive(payout)

        if method == "POST" and path == "/withdrawals":
            payload = self._read_json()
            payout = self.system.withdrawal_service.initiate_withdrawal(
                user_id=payload["userId"],
                amount=payload["amount"],
                idempotency_key=payload["idempotencyKey"],
            )
            return HTTPStatus.CREATED, to_primitive(payout)

        if method == "POST" and path.startswith("/withdrawals/") and path.endswith("/status"):
            payout_id = path.split("/")[2]
            payload = self._read_json()
            result = self.system.withdrawal_service.update_withdrawal_status(
                payout_id=payout_id,
                new_status=PayoutStatus(payload["status"]),
            )
            return HTTPStatus.OK, to_primitive(result)

        if method == "GET" and path.startswith("/users/") and path.endswith("/wallet"):
            user_id = path.split("/")[2]
            return HTTPStatus.OK, to_primitive(self.system.get_user_summary(user_id))

        raise NotFoundError("Route not found.")

    def _read_json(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValidationError(f"Invalid JSON payload: {error.msg}") from error
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object.")
        return payload

    def _send_json(self, status_code: int, body: Dict[str, Any]) -> None:
        encoded = json.dumps(body, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), PayoutApiHandler)
    print(f"Payout API server running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return server
