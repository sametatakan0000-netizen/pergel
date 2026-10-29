"""Egress enforcement lifecycle: proxy server + netns, wired to the engine path.

Runs the policy-backed relay as a real proxy in a background thread, and
(optionally) sets up the network namespace via sudo. This is what imports the
policy/relay/netns layers into the actual serving path.
"""


import atexit
import os
import subprocess
import threading
from typing import Optional

from .egress_proxy import EgressPolicy
from .egress_relay import handle_client


def _sudo_run(script: str) -> None:
    """Run a shell script as root using the SUDO_PASSWORD convention."""
    env_path = os.path.expanduser("~/.hermes/.env")
    if not os.path.exists(env_path):
        raise RuntimeError("sudo env not available")
    cmd = (f'set -a; . {env_path} && set +a; '
           f'echo "$SUDO_PASSWORD" | sudo -S -p "" sh -c {script!r}')
    subprocess.run(["sh", "-c", cmd], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class EgressGuard:
    """Live egress enforcement: policy + relay proxy, optionally behind netns."""

    def __init__(self, policy: Optional[EgressPolicy] = None, *,
                 listen_host: str = "0.0.0.0", listen_port: int = 8899):
        self._policy = policy or EgressPolicy()
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._server = None
        self._loop = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._listen_port

    def start(self) -> int:
        """Start the proxy in a background thread. Returns the bound port."""
        import asyncio

        policy = self._policy
        ready = threading.Event()
        error: list = []

        async def _serve():
            async def handler(reader, writer):
                await handle_client(reader, writer, policy)
            try:
                self._server = await asyncio.start_server(
                    handler, self._listen_host, self._listen_port)
            except OSError as exc:
                error.append(exc)
                ready.set()
                return
            self._listen_port = self._server.sockets[0].getsockname()[1]
            ready.set()  # bind done: port is now real, safe to hand out
            async with self._server:
                try:
                    await self._server.serve_forever()
                except asyncio.CancelledError:
                    pass  # normal shutdown via stop()

        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(_serve())
            except Exception:
                ready.set()

        self._thread = threading.Thread(target=_run, name="egress-proxy", daemon=True)
        self._thread.start()
        if not ready.wait(timeout=10):
            raise RuntimeError("egress proxy failed to bind within 10s")
        if error:
            raise RuntimeError(f"egress proxy bind failed: {error[0]}") from error[0]
        atexit.register(self.stop)
        return self._listen_port

    def stop(self) -> None:
        if self._loop and self._server:
            try:
                self._loop.call_soon_threadsafe(self._server.close)
            except Exception:
                pass
        self._server = None


_current_guard: Optional[EgressGuard] = None


def start_egress_guard(*, use_netns: bool = True,
                       policy: Optional[EgressPolicy] = None,
                       proxy_port: int = 8899) -> EgressGuard:
    """Activate enforcement: start the proxy and (optionally) the namespace."""
    global _current_guard
    # Never bind 0.0.0.0: the relay must only be reachable from the netns
    # veth (netns mode) or loopback (no-netns). Otherwise it is LAN-exposed.
    bind = "10.255.255.1" if use_netns else "127.0.0.1"
    guard = EgressGuard(policy, listen_host=bind, listen_port=proxy_port)
    guard.start()
    if use_netns:
        from .netns import plan_netns
        script = plan_netns(
            namespace="bf_engine", veth_host="bfh0", veth_ns="bfns0",
            host_ip="10.255.255.1", ns_ip="10.255.255.2",
            proxy_host="10.255.255.1", proxy_port=guard.port)
        _sudo_run(script)
        atexit.register(_teardown_netns)
    _current_guard = guard
    return guard


def _teardown_netns() -> None:
    from .netns import plan_teardown
    try:
        _sudo_run(plan_teardown(namespace="bf_engine", veth_host="bfh0"))
    except Exception:
        pass
