import re
import socket
import subprocess

from core import CONFIG

KEEPALIVE_ENABLE = CONFIG['KEEPALIVE_ENABLE']
WAN_SOCKET_BUFFER_BYTES = int(CONFIG.get('WAN_SOCKET_BUFFER_BYTES', 8 * 1024 * 1024))
WAN_USER_TIMEOUT_MS = int(CONFIG.get('WAN_USER_TIMEOUT_MS', 30_000))


def _tune_wan_socket(sock):
    """Apply WAN-friendly socket tuning.

    - Leaves Nagle ON (do NOT set TCP_NODELAY) so bulk writes coalesce.
    - Raises SO_SNDBUF / SO_RCVBUF so the kernel can fill high-BDP pipes.
    - Sets TCP_USER_TIMEOUT on Linux so dead connections are detected
      faster than the ~2-minute kernel default.
    """
    if WAN_SOCKET_BUFFER_BYTES > 0:
        for opt in (socket.SO_SNDBUF, socket.SO_RCVBUF):
            try:
                sock.setsockopt(socket.SOL_SOCKET, opt, WAN_SOCKET_BUFFER_BYTES)
            except OSError:
                pass
    if KEEPALIVE_ENABLE:
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError:
            pass
    user_timeout = getattr(socket, 'TCP_USER_TIMEOUT', None)
    if user_timeout is not None and WAN_USER_TIMEOUT_MS > 0:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, user_timeout, WAN_USER_TIMEOUT_MS)
        except OSError:
            pass


def _normalize_host(host):
    """Strip brackets from IPv6 address notation, e.g. [::1] -> ::1."""
    host = host.strip()
    if host.startswith('[') and host.endswith(']'):
        return host[1:-1]
    return host


def _split_ipv6_scope(addr):
    """Split IPv6 scoped address into (base, scope), e.g. fe80::1%wlan0."""
    if '%' not in addr:
        return addr, None
    base, scope = addr.split('%', 1)
    return base, scope or None


def validate_ip(ip):
    """Validate IPv4 or IPv6 address."""
    if not ip:
        return False
    addr = _normalize_host(ip)
    try:
        socket.inet_pton(socket.AF_INET, addr)
        return True
    except OSError:
        pass
    ipv6_addr, scope = _split_ipv6_scope(addr)
    if scope and not re.match(r'^[A-Za-z0-9_.:-]+$', scope):
        return False
    try:
        socket.inet_pton(socket.AF_INET6, ipv6_addr)
        return True
    except OSError:
        return False


def validate_hostname(hostname):
    """Validate RFC-compatible hostname."""
    if not hostname or len(hostname) > 253:
        return False

    if hostname.endswith('.'):
        hostname = hostname[:-1]

    labels = hostname.split('.')
    allowed = re.compile(r'^[A-Za-z0-9-]{1,63}$')

    for label in labels:
        if not label:
            return False
        if label.startswith('-') or label.endswith('-'):
            return False
        if not allowed.match(label):
            return False

    return True


def validate_target_host(target):
    """Validate IPv4, IPv6 (with or without brackets), or DNS hostname."""
    if not target:
        return False
    target = target.strip()
    return validate_ip(target) or validate_hostname(target)


def validate_port(value):
    """Validate TCP port range."""
    try:
        port = int(value)
        return 1 <= port <= 65535
    except Exception:
        return False


def resolve_host(host, port):
    """
    Resolve host to a list of (family, sockaddr) using getaddrinfo.
    IPv6 results are preferred (listed first).
    Accepts raw IPv6 addresses, bracketed IPv6, IPv4, and hostnames.
    """
    host = _normalize_host(host)
    infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    if not infos:
        raise socket.gaierror(f"Could not resolve host: {host}")

    ipv6 = [(f, s) for f, _, _, _, s in infos if f == socket.AF_INET6]
    ipv4 = [(f, s) for f, _, _, _, s in infos if f == socket.AF_INET]
    return ipv6 + ipv4


def create_socket(family=socket.AF_INET6):
    """Create and configure a WAN client socket for the given address family.

    Note: Nagle is intentionally left enabled (no TCP_NODELAY) because this
    socket carries bulk data — disabling Nagle hurts throughput on WAN links.
    """
    sock = socket.socket(family, socket.SOCK_STREAM)
    _tune_wan_socket(sock)
    return sock


def create_server_socket(local_ip, port):
    """
    Create a dual-stack server socket (IPv6 + IPv4) when no specific IP is given.
    When a specific IP is given, binds to that address using the correct family.
    With IPV6_V6ONLY=0 the receiver accepts both IPv4-mapped and native IPv6 connections
    without any port forwarding when the peer has a global IPv6 address.
    """
    if local_ip and local_ip not in ('', '::', '0.0.0.0'):
        addr = _normalize_host(local_ip)
        try:
            socket.inet_pton(socket.AF_INET6, addr)
            family = socket.AF_INET6
        except OSError:
            family = socket.AF_INET

        server_socket = socket.socket(family, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _tune_wan_socket(server_socket)
        server_socket.bind((addr, port))
    else:
        # Dual-stack: AF_INET6 with IPV6_V6ONLY=0 accepts IPv4 and IPv6 on all interfaces.
        server_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _tune_wan_socket(server_socket)
        server_socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        server_socket.bind(('', port))

    return server_socket


def get_local_ipv6(include_link_local=False):
    """
    Return the first IPv6 address on this machine.
    By default this prefers global scope and ignores link-local addresses.
    If include_link_local=True, falls back to link-local scope when no global address exists.
    """
    try:
        result = subprocess.run(
            ['ip', '-6', 'addr', 'show', 'scope', 'global'],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith('inet6'):
                addr = line.split()[1].split('/')[0]
                if addr and addr != '::1':
                    return addr
    except Exception:
        pass

    if include_link_local:
        try:
            result = subprocess.run(
                ['ip', '-6', 'addr', 'show', 'scope', 'link'],
                capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith('inet6'):
                    addr = line.split()[1].split('/')[0]
                    if addr and addr != '::1':
                        return addr
        except Exception:
            pass

    # Fallback: probe outbound IPv6 route
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.settimeout(2)
        sock.connect(('2001:4860:4860::8888', 80))
        addr = sock.getsockname()[0]
        sock.close()
        if addr and addr != '::1':
            return addr
    except Exception:
        pass

    return None


def get_shareable_ipv6():
    """
    Return the best IPv6 address to share for WAN mode.

    Preference order:
    1. Global IPv6 (internet-routable)
    2. Link-local IPv6 with interface scope (local network only)

    Returns dict with keys:
      - address: IPv6 string to share (link-local includes %iface)
      - scope: 'global' or 'link-local'
      - note: user-facing guidance
    or None if no IPv6 is available.
    """
    try:
        result = subprocess.run(
            ['ip', '-6', '-o', 'addr', 'show', 'scope', 'global'],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[2] == 'inet6':
                iface = parts[1]
                addr = parts[3].split('/')[0]
                if addr and addr != '::1':
                    return {
                        'address': addr,
                        'scope': 'global',
                        'note': f'Global IPv6 on {iface} (share this over internet)'
                    }
    except Exception:
        pass

    try:
        result = subprocess.run(
            ['ip', '-6', '-o', 'addr', 'show', 'scope', 'link'],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[2] == 'inet6':
                iface = parts[1]
                addr = parts[3].split('/')[0]
                if addr and addr != '::1' and iface != 'lo':
                    return {
                        'address': f'{addr}%{iface}',
                        'scope': 'link-local',
                        'note': f'Link-local IPv6 on {iface} (same LAN only)'
                    }
    except Exception:
        pass

    return None
