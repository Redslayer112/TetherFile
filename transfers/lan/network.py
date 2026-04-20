import socket
import sys

try:
    import psutil
except ImportError:
    print("❌ Missing dependency: psutil")
    print("📦 Install with: pip install psutil")
    sys.exit(1)

from core import CONFIG

KEEPALIVE_ENABLE = CONFIG['KEEPALIVE_ENABLE']

# -----------------------------------------------------------------------------
# Internal cache (prevents repeated work, essentially free speed-up)
# -----------------------------------------------------------------------------
_INTERFACE_DESC_CACHE = {}

def get_all_network_interfaces():
    """
    Get all LAN network interfaces (WiFi and Ethernet only).
    Excludes: Virtual, Bluetooth, USB, Mobile, etc.
    """
    interfaces = []

    try:
        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()

        for interface_name, addr_list in net_if_addrs.items():
            # Skip loopback interfaces
            if interface_name.lower() in ('lo', 'loopback'):
                continue

            # Interface must be UP
            stats = net_if_stats.get(interface_name)
            if stats and not stats.isup:
                continue

            for addr in addr_list:
                if addr.family != socket.AF_INET:
                    continue

                ip = addr.address

                # Skip loopback & link-local
                if ip.startswith('127.') or ip.startswith('169.254.'):
                    continue

                # Skip Bluetooth and USB
                if _is_bluetooth_or_usb(interface_name):
                    continue

                description = get_interface_description(interface_name)

                # ✅ ONLY allow real LAN interfaces
                if description not in ("📶 WiFi Network", "🔌 Ethernet Network"):
                    continue

                interfaces.append(
                    (description, ip, interface_name)
                )

    except Exception as e:
        print(f"Error getting network interfaces: {e}")

    return interfaces


def get_interface_description(interface_name):
    """
    Fast, non-blocking interface description.
    Uses naming heuristics only (cached).
    """
    if interface_name in _INTERFACE_DESC_CACHE:
        return _INTERFACE_DESC_CACHE[interface_name]

    desc = _categorize_interface("", interface_name)
    _INTERFACE_DESC_CACHE[interface_name] = desc
    return desc


def _is_bluetooth_or_usb(interface_name):
    """
    Check if interface is Bluetooth or USB (handled by other modules).
    Returns True if interface should be skipped.
    """
    name_lower = interface_name.lower()
    
    # Bluetooth indicators
    bluetooth_indicators = ['bluetooth', 'bnep', 'bt']
    if any(i in name_lower for i in bluetooth_indicators):
        return True
    
    # USB indicators
    usb_indicators = ['usb', 'rndis', 'cdc_ether']
    if any(i in name_lower for i in usb_indicators):
        return True
    
    return False


def _categorize_interface(description, interface_name):
    """
    Categorize interface type based on description and name.
    Returns a user-friendly description with emoji.
    Only returns WiFi, Ethernet, or Virtual (no Bluetooth/USB - handled elsewhere).
    """
    name_lower = interface_name.lower()
    desc_lower = description.lower()

    # WiFi/Wireless indicators
    wifi_indicators = [
        'wifi', 'wireless', 'wlan', '802.11', 'wi-fi', 'wl',
        'ath', 'iwl', 'rtl8188', 'rtl8192', 'bcm'
    ]
    if any(i in name_lower or i in desc_lower for i in wifi_indicators):
        return "📶 WiFi Network"

    # Ethernet indicators
    ethernet_indicators = [
        'ethernet', 'eth', 'en', 'lan',
        'realtek', 'intel', 'broadcom', 'e1000',
        'rtl8139', 'rtl8169'
    ]
    if any(i in name_lower or i in desc_lower for i in ethernet_indicators):
        return "🔌 Ethernet Network"

    # Virtual/Tunnel indicators
    virtual_indicators = [
        'virtual', 'vmware', 'virtualbox', 'vbox',
        'hyper-v', 'tap', 'tun', 'bridge',
        'docker', 'veth'
    ]
    if any(i in name_lower or i in desc_lower for i in virtual_indicators):
        return "💻 Virtual Network"

    # Mobile/Cellular indicators
    mobile_indicators = ['mobile', 'cellular', '3g', '4g', '5g', 'lte', 'wwan', 'ppp']
    if any(i in name_lower or i in desc_lower for i in mobile_indicators):
        return "📱 Mobile Network"

    # Default based on common interface naming patterns
    if name_lower.startswith(('eth', 'en')):
        return "🔌 Ethernet Network"
    if name_lower.startswith(('wlan', 'wl', 'wi')):
        return "📶 WiFi Network"
    if name_lower.startswith(('vmnet', 'vbox', 'docker', 'br-')):
        return "💻 Virtual Network"

    return "🌐 Network Interface"


def validate_ip(ip):
    """Validate IP address format"""
    try:
        parts = ip.split('.')
        return len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts)
    except Exception:
        return False


def create_socket(local_ip=None):
    """Create and configure a socket"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    if KEEPALIVE_ENABLE:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    if local_ip:
        sock.bind((local_ip, 0))
    return sock


def create_server_socket(local_ip, port):
    """Create and configure a server socket"""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    if KEEPALIVE_ENABLE:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    if local_ip:
        server_socket.bind((local_ip, port))
    else:
        server_socket.bind(('', port))

    return server_socket