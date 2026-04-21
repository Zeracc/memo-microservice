from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import asyncpg
import httpx
from redis import Redis


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    details: dict[str, Any] = field(default_factory=dict)


class Phase1Validator:
    def __init__(
        self,
        *,
        api_base_url: str,
        postgres_dsn: str,
        redis_url: str,
        job_ttl_seconds: int,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.postgres_dsn = postgres_dsn
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.job_ttl_seconds = job_ttl_seconds
        self.results: list[CheckResult] = []

    def run(self) -> list[CheckResult]:
        with httpx.Client(timeout=10.0) as client:
            self._wait_for_api(client)
            self._record_health(client)
            self._record_structure_checks()
            self._record_invalid_payload(client)
            success = self._record_success_flow(client)
            self._record_idempotency(client, success)
            self._record_without_external_id(client)
            functional_failure = self._record_failure_flow(
                client,
                external_id="pedido-funcional",
                recipient="553199990000",
                message="invalid recipient",
                expected_notification_status="failed",
                expected_job_status="failed",
            )
            self._record_retry_flow(client)
            self._record_volume(client)
            self._record_job_expiration(client, success["job_id"])
            self._record_panel_queries(client, success["notification_id"], success["external_id"])
            self._record_consistency(success, functional_failure)

        return self.results

    def _wait_for_api(self, client: httpx.Client) -> None:
        deadline = time.time() + 30
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                response = client.get(f"{self.api_base_url}/health")
                if response.status_code == 200:
                    return
            except Exception as exc:  # pragma: no cover - runtime-only
                last_error = exc
            time.sleep(0.5)
        raise RuntimeError(f"API did not become healthy in time: {last_error}")

    def _record_health(self, client: httpx.Client) -> None:
        response = client.get(f"{self.api_base_url}/health")
        self._add(
            "health_endpoint",
            response.status_code == 200 and response.json().get("status") == "ok",
            status_code=response.status_code,
            body=response.json(),
        )

    def _record_structure_checks(self) -> None:
        details = asyncio.run(self._structure_checks())
        self._add(
            "database_structure",
            details["table_exists"]
            and details["indexes_ok"]
            and details["constraints_ok"]
            and details["trigger_ok"],
            **details,
        )

    async def _structure_checks(self) -> dict[str, Any]:
        connection = await asyncpg.connect(self.postgres_dsn)
        try:
            table_exists = await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='notifications')"
            )
            indexes = await connection.fetch(
                "SELECT indexname FROM pg_indexes WHERE tablename='notifications' ORDER BY indexname"
            )
            constraints = await connection.fetch(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'notifications'::regclass ORDER BY conname"
            )
            triggers = await connection.fetch(
                "SELECT trigger_name FROM information_schema.triggers WHERE event_object_table='notifications'"
            )
            return {
                "table_exists": bool(table_exists),
                "indexes": [row["indexname"] for row in indexes],
                "indexes_ok": {
                    "notifications_pkey",
                    "uq_notifications_external_id_not_null",
                    "ix_notifications_status_created_at",
                    "ix_notifications_recipient_created_at",
                    "ix_notifications_last_job_id",
                }.issubset({row["indexname"] for row in indexes}),
                "constraints": [row["conname"] for row in constraints],
                "constraints_ok": {
                    "chk_notifications_status",
                    "chk_notifications_type",
                    "chk_notifications_priority",
                }.issubset({row["conname"] for row in constraints}),
                "triggers": [row["trigger_name"] for row in triggers],
                "trigger_ok": "trg_notifications_updated_at" in {row["trigger_name"] for row in triggers},
            }
        finally:
            await connection.close()

    def _record_invalid_payload(self, client: httpx.Client) -> None:
        invalid_payloads = [
            {"message": "sem recipient"},
            {"recipient": "5531999999999"},
            {"recipient": "abc", "message": "telefone invalido"},
            {"recipient": 123, "message": True},
        ]
        statuses = []
        for payload in invalid_payloads:
            response = client.post(f"{self.api_base_url}/notifications", json=payload)
            statuses.append(response.status_code)

        self._add(
            "invalid_payloads",
            all(status == 422 for status in statuses),
            statuses=statuses,
        )

    def _record_success_flow(self, client: httpx.Client) -> dict[str, Any]:
        payload = {
            "external_id": "pedido-123",
            "recipient": "5531999999999",
            "message": "Seu pedido foi aprovado",
            "priority": "normal",
            "metadata": {"order_id": 123},
        }
        response = client.post(f"{self.api_base_url}/notifications", json=payload)
        body = response.json()
        notification_id = body["notification_id"]
        job_id = body["job_id"]
        final_notification, final_job = self._wait_for_terminal_state(client, notification_id, job_id)
        ttl = self.redis.ttl(f"job:{job_id}")
        row = asyncio.run(self._fetch_notification(notification_id))

        self._add(
            "success_flow",
            response.status_code == 202
            and body["status"] == "pending"
            and ttl > 0
            and final_notification["status"] == "sent"
            and final_job["status"] == "completed",
            response_status=response.status_code,
            create_body=body,
            final_notification=final_notification,
            final_job=final_job,
            job_ttl=ttl,
            database_row=row,
        )
        return {
            "notification_id": notification_id,
            "job_id": job_id,
            "external_id": payload["external_id"],
            "final_notification": final_notification,
            "final_job": final_job,
        }

    def _record_idempotency(self, client: httpx.Client, success: dict[str, Any]) -> None:
        payload = {
            "external_id": success["external_id"],
            "recipient": "5531999999999",
            "message": "Seu pedido foi aprovado",
            "priority": "normal",
            "metadata": {"order_id": 123},
        }
        response = client.post(f"{self.api_base_url}/notifications", json=payload)
        body = response.json()
        count = asyncio.run(self._count_notifications_by_external_id(success["external_id"]))
        queue_ttl = self.redis.ttl(f"job:{success['job_id']}")
        self._add(
            "idempotency_same_external_id",
            response.status_code == 202
            and body["already_exists"] is True
            and body["notification_id"] == success["notification_id"]
            and count == 1,
            response_status=response.status_code,
            body=body,
            count=count,
            original_job_ttl=queue_ttl,
        )

    def _record_without_external_id(self, client: httpx.Client) -> None:
        payload = {
            "recipient": "5531999998888",
            "message": "Notificacao sem external_id",
            "priority": "normal",
        }
        first = client.post(f"{self.api_base_url}/notifications", json=payload).json()
        second = client.post(f"{self.api_base_url}/notifications", json=payload).json()
        self._add(
            "without_external_id_creates_distinct_notifications",
            first["notification_id"] != second["notification_id"],
            first=first,
            second=second,
        )

    def _record_failure_flow(
        self,
        client: httpx.Client,
        *,
        external_id: str,
        recipient: str,
        message: str,
        expected_notification_status: str,
        expected_job_status: str,
    ) -> dict[str, Any]:
        payload = {
            "external_id": external_id,
            "recipient": recipient,
            "message": message,
            "priority": "normal",
        }
        response = client.post(f"{self.api_base_url}/notifications", json=payload)
        body = response.json()
        final_notification, final_job = self._wait_for_terminal_state(
            client,
            body["notification_id"],
            body["job_id"],
            timeout_seconds=20,
        )
        self._add(
            f"failure_flow_{external_id}",
            response.status_code == 202
            and final_notification["status"] == expected_notification_status
            and final_job["status"] == expected_job_status
            and final_notification["error_message"],
            create_body=body,
            final_notification=final_notification,
            final_job=final_job,
        )
        return {
            "notification_id": body["notification_id"],
            "job_id": body["job_id"],
            "final_notification": final_notification,
            "final_job": final_job,
        }

    def _record_retry_flow(self, client: httpx.Client) -> None:
        failure = self._record_failure_flow(
            client,
            external_id="pedido-retry",
            recipient="5531999997777",
            message="retry please",
            expected_notification_status="failed",
            expected_job_status="failed",
        )
        progress_history = failure["final_job"]["progress_history"]
        retry_events = [event for event in progress_history if event["phase"] == "retrying"]
        self._add(
            "retry_flow",
            len(retry_events) >= 1 and failure["final_notification"]["attempt_count"] >= 2,
            retry_events=len(retry_events),
            attempt_count=failure["final_notification"]["attempt_count"],
            final_notification=failure["final_notification"],
        )

    def _record_volume(self, client: httpx.Client) -> None:
        created: list[dict[str, Any]] = []
        for index in range(5):
            payload = {
                "external_id": f"volume-{index}",
                "recipient": f"55319999990{index:02d}",
                "message": f"volume test {index}",
                "priority": "normal",
            }
            response = client.post(f"{self.api_base_url}/notifications", json=payload)
            created.append(response.json())

        terminal_statuses = []
        for item in created:
            notification, job = self._wait_for_terminal_state(
                client,
                item["notification_id"],
                item["job_id"],
                timeout_seconds=20,
            )
            terminal_statuses.append((notification["status"], job["status"]))

        self._add(
            "volume_basic",
            len({item["notification_id"] for item in created}) == 5
            and all(statuses == ("sent", "completed") for statuses in terminal_statuses),
            created=created,
            terminal_statuses=terminal_statuses,
        )

    def _record_job_expiration(self, client: httpx.Client, job_id: str) -> None:
        time.sleep(self.job_ttl_seconds + 2)
        response = client.get(f"{self.api_base_url}/jobs/{job_id}")
        self._add(
            "job_expiration",
            response.status_code == 404,
            status_code=response.status_code,
            body=response.json(),
        )

    def _record_panel_queries(self, client: httpx.Client, notification_id: str, external_id: str) -> None:
        by_id = client.get(f"{self.api_base_url}/notifications/{notification_id}")
        listing = client.get(
            f"{self.api_base_url}/notifications",
            params={"external_id": external_id, "status": "sent", "page": 1, "limit": 10},
        )
        self._add(
            "panel_queries",
            by_id.status_code == 200
            and listing.status_code == 200
            and listing.json()["total"] >= 1,
            by_id=by_id.json(),
            listing=listing.json(),
        )

    def _record_consistency(self, success: dict[str, Any], failure: dict[str, Any]) -> None:
        self._add(
            "status_consistency",
            success["final_notification"]["status"] == "sent"
            and success["final_job"]["status"] == "completed"
            and failure["final_notification"]["status"] == "failed"
            and failure["final_job"]["status"] == "failed",
            success_notification_status=success["final_notification"]["status"],
            success_job_status=success["final_job"]["status"],
            failure_notification_status=failure["final_notification"]["status"],
            failure_job_status=failure["final_job"]["status"],
        )

    def _wait_for_terminal_state(
        self,
        client: httpx.Client,
        notification_id: str,
        job_id: str,
        *,
        timeout_seconds: int = 15,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        deadline = time.time() + timeout_seconds
        last_notification: dict[str, Any] | None = None
        last_job: dict[str, Any] | None = None
        while time.time() < deadline:
            notification_response = client.get(f"{self.api_base_url}/notifications/{notification_id}")
            job_response = client.get(f"{self.api_base_url}/jobs/{job_id}")
            last_notification = notification_response.json()
            last_job = job_response.json()
            if (
                last_notification.get("status") in {"sent", "failed"}
                and last_job.get("status") in {"completed", "failed"}
            ):
                return last_notification, last_job
            time.sleep(0.5)
        raise RuntimeError(
            f"Timed out waiting for terminal state notification={last_notification} job={last_job}"
        )

    async def _fetch_notification(self, notification_id: str) -> dict[str, Any]:
        connection = await asyncpg.connect(self.postgres_dsn)
        try:
            row = await connection.fetchrow(
                """
                SELECT id, external_id, status, provider, attempt_count, created_at, updated_at, sent_at, failed_at
                FROM notifications
                WHERE id = $1::uuid
                """,
                notification_id,
            )
            if row is None:
                return {}
            return dict(row)
        finally:
            await connection.close()

    async def _count_notifications_by_external_id(self, external_id: str) -> int:
        connection = await asyncpg.connect(self.postgres_dsn)
        try:
            return int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM notifications WHERE external_id = $1",
                    external_id,
                )
            )
        finally:
            await connection.close()

    def _add(self, name: str, ok: bool, **details: Any) -> None:
        self.results.append(CheckResult(name=name, ok=ok, details=details))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--postgres-dsn", default="postgresql://postgres:postgres@localhost:5432/memo")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--job-ttl-seconds", type=int, default=15)
    args = parser.parse_args()

    validator = Phase1Validator(
        api_base_url=args.api_base_url,
        postgres_dsn=args.postgres_dsn,
        redis_url=args.redis_url,
        job_ttl_seconds=args.job_ttl_seconds,
    )
    results = validator.run()
    summary = {
        "checks": [asdict(result) for result in results],
        "all_passed": all(result.ok for result in results),
    }
    print(json.dumps(summary, ensure_ascii=False, default=str, indent=2))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
