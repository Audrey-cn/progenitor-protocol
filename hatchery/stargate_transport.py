from __future__ import annotations

import os
import time
from typing import Optional
from urllib import error, request

# [F004] Hard cap on any fetched body to prevent OOM / disk-fill from a hostile gateway.
MAX_GENE_BYTES = int(os.environ.get("PROGENITOR_MAX_GENE_BYTES", str(8 * 1024 * 1024)))


def _read_capped(response, limit: int = MAX_GENE_BYTES) -> bytes:
    """Read at most ``limit`` bytes; raise if the body exceeds it (DoS guard)."""
    data = response.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError(f"Stargate response exceeds {limit} bytes — refusing (possible DoS)")
    return data


def build_gateway_url(content_id: str, gateway_base: str) -> str:
    if not content_id or not content_id.strip():
        raise ValueError("content_id is required for Stargate transport")
    return f"{gateway_base.rstrip('/')}/{content_id.strip()}"


def probe_kubo_alive(kubo_api_url: str) -> bool:
    try:
        req = request.Request(f"{kubo_api_url}?quiet=true", method="POST")
        with request.urlopen(req, timeout=3):
            pass
        return True
    except (error.HTTPError, error.URLError, OSError):
        return False


def pull_via_kubo(content_id: str, *, timeout_sec: int) -> Optional[bytes]:
    kubo_cat_url = "http://127.0.0.1:5001/api/v0/cat"
    try:
        req = request.Request(
            f"{kubo_cat_url}?arg={content_id}",
            headers={"User-Agent": "G012-akashic-receptor/1.9"},
            method="POST",
        )
        with request.urlopen(req, timeout=timeout_sec) as response:
            return _read_capped(response)
    except (error.HTTPError, error.URLError, TimeoutError, RuntimeError):
        return None


def pull_via_gateway_array(
    content_id: str,
    *,
    gateways: list[str],
    kubo_api_url: str,
    timeout_sec: int,
    retry_policy: dict,
) -> bytes:
    if probe_kubo_alive(kubo_api_url):
        local_data = pull_via_kubo(content_id, timeout_sec=timeout_sec)
        if local_data:
            return local_data

    max_retries = int(retry_policy.get("max_retries", 1))
    backoff = float(retry_policy.get("backoff_factor", 1.0))
    all_errors = []

    for gate_idx, gateway_base in enumerate(gateways, start=1):
        url = build_gateway_url(content_id, gateway_base)
        for attempt in range(1, max_retries + 1):
            try:
                req = request.Request(
                    url,
                    headers={"User-Agent": "G012-akashic-receptor/1.2"},
                )
                with request.urlopen(req, timeout=timeout_sec) as response:
                    return _read_capped(response)
            except error.URLError as exc:
                all_errors.append(f"[gateway {gate_idx}] URLError: {exc}")
            except TimeoutError as exc:
                all_errors.append(f"[gateway {gate_idx}] Timeout: {exc}")

            if attempt < max_retries:
                time.sleep(backoff * attempt)

    raise RuntimeError(
        f"Stargate transport failed for [{content_id}] across {len(gateways)} gateways. "
        f"errors: {'; '.join(all_errors)}"
    )
