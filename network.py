import socket
import platform
import subprocess
import json
import sys

try:
    import psutil
except ImportError:
    print("❌ Missing dependency: psutil")
    print("📦 Install with: pip install psutil")
    sys.exit(1)


def get_all_network_interfaces():
    """
    Get all network interfaces with IP addresses across all platforms.
    Returns list of tuples: (description, adapter_name, ip_address, interface_id)
    """
    interfaces = []
    
    try:
        # Get network interface addresses
        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()
        
        for interface_name, addr_list in net_if_addrs.items():
            # Skip loopback interfaces
            if interface_name.lower() in ['lo', 'loopback']:
                continue
                
            # Get IPv4 addresses
            ipv4_addrs = [addr for addr in addr_list if addr.family == socket.AF_INET]
            
            for addr in ipv4_addrs:
                ip = addr.address
                
                # Skip loopback IPs and link-local addresses
                if ip == '127.0.0.1' or ip.startswith('127.') or ip.startswith('169.254.'):
                    continue
                
                # Get interface statistics for additional info
                is_up = net_if_stats.get(interface_name, {}).isup if interface_name in net_if_stats else True
                
                # Only include interfaces that are up
                if not is_up:
                    continue
                
                # Get human-readable description
                description = get_interface_description(interface_name)
                
                interfaces.append((description, interface_name, ip, interface_name))
    
    except Exception as e:
        print(f"Error getting network interfaces: {e}")
    
    return interfaces


def get_interface_description(interface_name):
    """
    Get human-readable description for network interface based on platform
    """
    system = platform.system().lower()
    
    try:
        if system == "windows":
            return _get_windows_interface_description(interface_name)
        elif system == "darwin":  # macOS
            return _get_macos_interface_description(interface_name)
        elif system == "linux":
            return _get_linux_interface_description(interface_name)
        else:
            return _get_generic_interface_description(interface_name)
    except Exception:
        return _get_generic_interface_description(interface_name)


def _get_windows_interface_description(interface_name):
    """Get Windows-specific interface description"""
    try:
        # Try to get detailed info using PowerShell
        cmd = f'powershell "Get-NetAdapter -Name \\"{interface_name}\\" | Select-Object InterfaceDescription | ConvertTo-Json"'
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=3)
        
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            desc = data.get('InterfaceDescription', '')
            if desc:
                return _categorize_interface(desc, interface_name)
    except Exception:
        pass
    
    return _get_generic_interface_description(interface_name)


def _get_macos_interface_description(interface_name):
    """Get macOS-specific interface description"""
    try:
        # Try to get interface info using networksetup
        cmd = f"networksetup -listallhardwareports | grep -A 1 '{interface_name}'"
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=3)
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'Hardware Port:' in line:
                    desc = line.split('Hardware Port:')[1].strip()
                    return _categorize_interface(desc, interface_name)
    except Exception:
        pass
    
    return _get_generic_interface_description(interface_name)


def _get_linux_interface_description(interface_name):
    """Get Linux-specific interface description"""
    try:
        # Try to read from /sys/class/net
        desc_path = f"/sys/class/net/{interface_name}/device/uevent"
        try:
            with open(desc_path, 'r') as f:
                content = f.read()
                for line in content.split('\n'):
                    if 'DRIVER=' in line:
                        driver = line.split('DRIVER=')[1].strip()
                        return _categorize_interface(driver, interface_name)
        except:
            pass
        
        # Alternative: try ethtool for more info
        cmd = f"ethtool -i {interface_name} 2>/dev/null | grep driver"
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=2)
        
        if result.returncode == 0 and result.stdout.strip():
            driver = result.stdout.split(':')[1].strip()
            return _categorize_interface(driver, interface_name)
            
    except Exception:
        pass
    
    return _get_generic_interface_description(interface_name)


def _get_generic_interface_description(interface_name):
    """Get generic interface description based on interface name patterns"""
    return _categorize_interface("", interface_name)


def _categorize_interface(description, interface_name):
    """
    Categorize interface type based on description and name
    Returns a user-friendly description
    """
    name_lower = interface_name.lower()
    desc_lower = description.lower()
    
    # WiFi/Wireless indicators
    wifi_indicators = ['wifi', 'wireless', 'wlan', '802.11', 'wi-fi', 'wl', 'ath', 'iwl', 'rtl8188', 'rtl8192', 'bcm']
    if any(indicator in name_lower or indicator in desc_lower for indicator in wifi_indicators):
        return "📶 WiFi Network"
    
    # Ethernet indicators
    ethernet_indicators = ['ethernet', 'eth', 'en', 'lan', 'realtek', 'intel', 'broadcom', 'e1000', 'rtl8139', 'rtl8169']
    if any(indicator in name_lower or indicator in desc_lower for indicator in ethernet_indicators):
        return "🔌 Ethernet Network"
    
    # USB indicators
    usb_indicators = ['usb', 'rndis', 'cdc_ether']
    if any(indicator in name_lower or indicator in desc_lower for indicator in usb_indicators):
        return "🔌 USB Network"
    
    # Virtual/Tunnel indicators
    virtual_indicators = ['virtual', 'vmware', 'virtualbox', 'vbox', 'hyper-v', 'tap', 'tun', 'bridge', 'docker', 'veth']
    if any(indicator in name_lower or indicator in desc_lower for indicator in virtual_indicators):
        return "💻 Virtual Network"
    
    # Bluetooth indicators
    bluetooth_indicators = ['bluetooth', 'bnep', 'bt']
    if any(indicator in name_lower or indicator in desc_lower for indicator in bluetooth_indicators):
        return "📱 Bluetooth Network"
    
    # Mobile/Cellular indicators
    mobile_indicators = ['mobile', 'cellular', '3g', '4g', '5g', 'lte', 'wwan', 'ppp']
    if any(indicator in name_lower or indicator in desc_lower for indicator in mobile_indicators):
        return "📱 Mobile Network"
    
    # Default based on common interface naming patterns
    if name_lower.startswith(('eth', 'en')):
        return "🔌 Ethernet Network"
    elif name_lower.startswith(('wlan', 'wl', 'wi')):
        return "📶 WiFi Network"
    elif name_lower.startswith(('usb', 'rndis')):
        return "🔌 USB Network"
    elif name_lower.startswith(('vmnet', 'vbox', 'docker', 'br-')):
        return "💻 Virtual Network"
    else:
        return "🌐 Network Interface"


# Legacy function name for backward compatibility
def get_ethernet_interfaces():
    """
    Legacy function for backward compatibility.
    Now returns all network interfaces, not just Ethernet.
    """
    return get_all_network_interfaces()


def get_interface_name(interface_id):
    """
    Legacy function for backward compatibility.
    Get human-readable interface name (now returns description)
    """
    interfaces = get_all_network_interfaces()
    for desc, name, ip, iface_id in interfaces:
        if iface_id == interface_id:
            return f"{desc} - {name}"
    return interface_id[:8] + "..."


def validate_ip(ip):
    """Validate IP address format"""
    try:
        parts = ip.split('.')
        return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
    except:
        return False


def create_socket(local_ip=None):
    """Create and configure a socket"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if local_ip:
        sock.bind((local_ip, 0))
    return sock


def create_server_socket(local_ip, port):
    """Create and configure a server socket"""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    if local_ip:
        server_socket.bind((local_ip, port))
    else:
        server_socket.bind(('', port))
    
    return server_socket