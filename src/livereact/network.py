"""Network helpers for Pro DJ Link bring-up (docs/04 §7, docs/07).

Pro DJ Link is UDP on a link-local network. The reliable setup is a static
link-local IP on the host NIC (more dependable than waiting on APIPA), with the
firewall allowing the DJ-Link UDP ports. This module only *reports* — it never
changes OS network config; that's a manual step documented in HARDWARE.md.
"""

from __future__ import annotations

import logging
import socket

log = logging.getLogger(__name__)

DJLINK_PORTS = (50000, 50001, 50002)
LINK_LOCAL_PREFIX = "169.254."
RECOMMENDED_HOST_IP = "169.254.50.50"   # /16


def list_ipv4_addresses() -> list[tuple[str, str]]:
    """Best-effort list of (interface-ish, ipv4) for the host.

    Uses psutil when available (richer), else falls back to the primary address.
    """
    try:
        import psutil  # optional

        out: list[tuple[str, str]] = []
        for name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET:
                    out.append((name, a.address))
        return out
    except Exception:  # noqa: BLE001 - psutil optional / any failure -> fallback
        try:
            return [("default", socket.gethostbyname(socket.gethostname()))]
        except OSError:
            return []


def has_link_local(addresses: list[tuple[str, str]]) -> bool:
    return any(ip.startswith(LINK_LOCAL_PREFIX) for _, ip in addresses)


def diagnostics() -> str:
    """A human-readable readiness report for the DJ-Link network."""
    addrs = list_ipv4_addresses()
    lines = ["Pro DJ Link network check:"]
    for name, ip in addrs:
        flag = "  <- link-local (good)" if ip.startswith(LINK_LOCAL_PREFIX) else ""
        lines.append(f"  {name}: {ip}{flag}")
    if not has_link_local(addrs):
        lines.append(
            f"  WARNING: No link-local address found. Set the wired NIC to a static "
            f"{RECOMMENDED_HOST_IP}/255.255.0.0 and allow UDP {DJLINK_PORTS} through "
            f"the firewall (see HARDWARE.md)."
        )
    return "\n".join(lines)
