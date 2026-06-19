"""Long-running SofaScore API healthcheck.

This script intentionally measures raw request outcomes. Retries are disabled by
default so 403/429/5xx spikes are visible instead of being hidden by recovery.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from curl_cffi import requests

SOFASCORE_BASE_URL = "https://api.sofascore.com/api/v1"
DEFAULT_USER_AGENT = "WorldCupQuente/0.1"
WORLD_CUP_TOURNAMENT_ID = 16
WORLD_CUP_SEASON_ID = 58210
REFERENCE_TEAM_ID = 4748
REFERENCE_EVENT_ID = 15186709


@dataclass(frozen=True)
class Probe:
    name: str
    url: str
    schema: str
    provider: str = "sofascore"


@dataclass
class EndpointStats:
    total: int = 0
    ok: int = 0
    schema_failures: int = 0
    status_codes: Counter[str] = field(default_factory=Counter)
    errors: Counter[str] = field(default_factory=Counter)
    latencies_ms: list[int] = field(default_factory=list)
    consecutive_failures: int = 0
    max_consecutive_failures: int = 0

    def record(self, result: dict[str, Any]) -> None:
        self.total += 1
        self.status_codes[str(result.get("status_code") or "error")] += 1
        if result.get("error"):
            self.errors[str(result["error"])] += 1
        if result.get("latency_ms") is not None:
            self.latencies_ms.append(int(result["latency_ms"]))
        if not result.get("schema_ok"):
            self.schema_failures += 1
        if result.get("ok") and result.get("schema_ok"):
            self.ok += 1
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            self.max_consecutive_failures = max(self.max_consecutive_failures, self.consecutive_failures)


async def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    probes = build_probes()
    stats: dict[str, EndpointStats] = defaultdict(EndpointStats)
    deadline = time.monotonic() + (args.duration_hours * 3600) if args.duration_hours else None
    cycle = 0

    print(f"Starting SofaScore healthcheck with {len(probes)} probes")
    print(f"Output: {output_path}")

    try:
        with output_path.open("a", encoding="utf-8") as output_file:
            while True:
                cycle += 1
                cycle_started = time.monotonic()
                print(f"Cycle {cycle} started at {utc_now_iso()}")

                for probe in probes:
                    result = await run_probe(
                        probe,
                        timeout=args.timeout,
                        user_agent=args.user_agent,
                        retries=args.retries,
                    )
                    result["cycle"] = cycle
                    output_file.write(json.dumps(result, ensure_ascii=True, sort_keys=True) + "\n")
                    output_file.flush()
                    stats[probe.name].record(result)
                    print(format_probe_line(result))

                if args.cycles and cycle >= args.cycles:
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    break

                elapsed = time.monotonic() - cycle_started
                sleep_seconds = max(0.0, args.interval - elapsed)
                if deadline is not None:
                    sleep_seconds = min(sleep_seconds, max(0.0, deadline - time.monotonic()))
                if sleep_seconds <= 0:
                    continue
                await asyncio.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("Interrupted by user")

    print_summary(stats)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor SofaScore API availability and schema stability.")
    parser.add_argument("--interval", type=float, default=60.0, help="Seconds between probe cycles. Default: 60")
    parser.add_argument("--duration-hours", type=float, default=0.0, help="Total runtime in hours. Default: run until interrupted")
    parser.add_argument("--cycles", type=int, default=0, help="Number of cycles to run. Useful for smoke tests")
    parser.add_argument("--output", default="logs/sofascore_healthcheck.jsonl", help="JSONL output path")
    parser.add_argument("--timeout", type=float, default=float(os.getenv("REQUEST_TIMEOUT", "30")), help="Request timeout in seconds")
    parser.add_argument("--user-agent", default=os.getenv("HTTP_USER_AGENT", DEFAULT_USER_AGENT), help="User-Agent header")
    parser.add_argument("--retries", type=int, default=0, help="Retries per probe. Default: 0 to expose raw blocking")
    return parser.parse_args()


def build_probes() -> list[Probe]:
    today = datetime.now(UTC).date()
    tomorrow = today + timedelta(days=1)
    paths = [
        ("world_cup_teams", f"/unique-tournament/{WORLD_CUP_TOURNAMENT_ID}/season/{WORLD_CUP_SEASON_ID}/teams", "teams"),
        ("world_cup_events_last", f"/unique-tournament/{WORLD_CUP_TOURNAMENT_ID}/season/{WORLD_CUP_SEASON_ID}/events/last/0", "events"),
        ("world_cup_events_next", f"/unique-tournament/{WORLD_CUP_TOURNAMENT_ID}/season/{WORLD_CUP_SEASON_ID}/events/next/0", "events"),
        ("world_cup_standings", f"/unique-tournament/{WORLD_CUP_TOURNAMENT_ID}/season/{WORLD_CUP_SEASON_ID}/standings/total", "standings"),
        ("world_cup_rounds", f"/unique-tournament/{WORLD_CUP_TOURNAMENT_ID}/season/{WORLD_CUP_SEASON_ID}/rounds", "rounds"),
        ("scheduled_today", f"/sport/football/scheduled-events/{today.isoformat()}", "events"),
        ("scheduled_tomorrow", f"/sport/football/scheduled-events/{tomorrow.isoformat()}", "events"),
        ("team_profile", f"/team/{REFERENCE_TEAM_ID}", "team"),
        ("team_players", f"/team/{REFERENCE_TEAM_ID}/players", "players"),
        ("team_events_last", f"/team/{REFERENCE_TEAM_ID}/events/last/0", "events"),
        ("team_events_next", f"/team/{REFERENCE_TEAM_ID}/events/next/0", "events"),
        ("event_incidents", f"/event/{REFERENCE_EVENT_ID}/incidents", "incidents"),
        ("event_lineups", f"/event/{REFERENCE_EVENT_ID}/lineups", "lineups"),
        ("event_statistics", f"/event/{REFERENCE_EVENT_ID}/statistics", "statistics"),
    ]
    probes = [Probe(name=name, url=f"{SOFASCORE_BASE_URL}{path}", schema=schema) for name, path, schema in paths]

    return probes


async def run_probe(probe: Probe, timeout: float, user_agent: str, retries: int) -> dict[str, Any]:
    attempts = max(1, retries + 1)
    last_result: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        result = await _single_request(probe, timeout=timeout, user_agent=user_agent, attempt=attempt)
        last_result = result
        if result["ok"] and result["schema_ok"]:
            return result
        if attempt < attempts:
            await asyncio.sleep(min(2.0, 0.5 * attempt))
    return last_result or _error_result(probe, "NoResult", attempt=0)


async def _single_request(probe: Probe, timeout: float, user_agent: str, attempt: int) -> dict[str, Any]:
    started = time.perf_counter()
    headers = build_headers(probe.provider, user_agent)
    try:
        async with requests.AsyncSession(impersonate="chrome", timeout=timeout) as client:
            response = await client.get(probe.url, headers=headers)
        latency_ms = int((time.perf_counter() - started) * 1000)
        status_code = response.status_code
        response_bytes = len(response.content or b"")
        payload = None
        json_error = None
        if 200 <= status_code < 300:
            try:
                payload = response.json()
            except ValueError as exc:
                json_error = type(exc).__name__
        schema_ok, schema_error = validate_schema(payload, probe.schema)
        if json_error:
            schema_ok = False
            schema_error = json_error
        return {
            "timestamp": utc_now_iso(),
            "provider": probe.provider,
            "name": probe.name,
            "url": probe.url,
            "status_code": status_code,
            "ok": 200 <= status_code < 300,
            "latency_ms": latency_ms,
            "response_bytes": response_bytes,
            "schema": probe.schema,
            "schema_ok": schema_ok,
            "schema_error": schema_error,
            "attempt": attempt,
            "error": None,
        }
    except Exception as exc:
        result = _error_result(probe, type(exc).__name__, attempt=attempt)
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        result["error_detail"] = str(exc)[:500]
        return result


def _error_result(probe: Probe, error: str, attempt: int) -> dict[str, Any]:
    return {
        "timestamp": utc_now_iso(),
        "provider": probe.provider,
        "name": probe.name,
        "url": probe.url,
        "status_code": None,
        "ok": False,
        "latency_ms": None,
        "response_bytes": 0,
        "schema": probe.schema,
        "schema_ok": False,
        "schema_error": None,
        "attempt": attempt,
        "error": error,
    }


def build_headers(provider: str, user_agent: str) -> dict[str, str]:
    if provider == "sofascore":
        return {
            "Accept": "application/json",
            "Referer": "https://www.sofascore.com/",
            "x-requested-with": "XMLHttpRequest",
            "User-Agent": user_agent,
        }
    return {"Accept": "application/json", "User-Agent": user_agent}


def validate_schema(payload: Any, schema: str) -> tuple[bool, str | None]:
    if not isinstance(payload, dict):
        return False, "payload_not_object"
    validators = {
        "teams": lambda data: isinstance(data.get("teams"), list),
        "events": lambda data: isinstance(data.get("events"), list),
        "standings": lambda data: isinstance(data.get("standings"), list),
        "rounds": lambda data: isinstance(data.get("rounds"), list),
        "team": lambda data: isinstance(data.get("team"), dict),
        "players": lambda data: isinstance(data.get("players"), list),
        "incidents": lambda data: isinstance(data.get("incidents"), list),
        "lineups": lambda data: isinstance(data.get("home"), dict) or isinstance(data.get("away"), dict),
        "statistics": lambda data: isinstance(data.get("statistics"), list),
    }
    validator = validators.get(schema)
    if validator is None:
        return False, "unknown_schema"
    if validator(payload):
        return True, None
    return False, f"schema_{schema}_failed"


def format_probe_line(result: dict[str, Any]) -> str:
    status = result.get("status_code") if result.get("status_code") is not None else "ERR"
    ok = "ok" if result.get("ok") and result.get("schema_ok") else "fail"
    latency = result.get("latency_ms")
    latency_text = f"{latency}ms" if latency is not None else "-"
    error = result.get("error") or result.get("schema_error") or ""
    suffix = f" {error}" if error else ""
    return f"  {ok:4} {status!s:>3} {latency_text:>7} {result['name']}{suffix}"


def print_summary(stats: dict[str, EndpointStats]) -> None:
    total = sum(item.total for item in stats.values())
    ok = sum(item.ok for item in stats.values())
    schema_failures = sum(item.schema_failures for item in stats.values())
    all_statuses = Counter()
    all_errors = Counter()
    all_latencies: list[int] = []
    for item in stats.values():
        all_statuses.update(item.status_codes)
        all_errors.update(item.errors)
        all_latencies.extend(item.latencies_ms)

    success_rate = (ok / total * 100) if total else 0.0
    print("\nSummary")
    print(f"Total requests: {total}")
    print(f"Successful schema-valid requests: {ok}")
    print(f"Success rate: {success_rate:.2f}%")
    print(f"Schema failures: {schema_failures}")
    print(f"Status counts: {dict(sorted(all_statuses.items()))}")
    if all_errors:
        print(f"Errors: {dict(all_errors.most_common())}")
    if all_latencies:
        print(
            "Latency: "
            f"p50={percentile(all_latencies, 50)}ms "
            f"p95={percentile(all_latencies, 95)}ms "
            f"p99={percentile(all_latencies, 99)}ms"
        )

    worst = sorted(stats.items(), key=lambda pair: endpoint_success_rate(pair[1]))[:5]
    print("Worst endpoints:")
    for name, item in worst:
        print(
            f"  {name}: success={endpoint_success_rate(item):.2f}% "
            f"max_consecutive_failures={item.max_consecutive_failures} "
            f"statuses={dict(sorted(item.status_codes.items()))}"
        )


def endpoint_success_rate(stats: EndpointStats) -> float:
    return (stats.ok / stats.total * 100) if stats.total else 0.0


def percentile(values: list[int], percent: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * (percent / 100))
    return ordered[index]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
