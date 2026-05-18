import argparse
import ctypes
import json
import logging
import random
import subprocess
import sys
import time
import traceback
import winreg
from pathlib import Path


NETWORK_CLASS_GUID = r"{4d36e972-e325-11ce-bfc1-08002be10318}"
NETWORK_CLASS_REG_PATH = (
    r"SYSTEM\CurrentControlSet\Control\Class\\" + NETWORK_CLASS_GUID
)

LOGGER = logging.getLogger("WifiMacTool")


def get_script_folder() -> Path:
    try:
        return Path(__file__).resolve().parent
    except Exception:
        return Path.cwd()


def get_script_path() -> Path:
    try:
        return Path(__file__).resolve()
    except Exception:
        return Path(sys.argv[0]).resolve()


def get_log_file_path() -> Path:
    return get_script_folder() / "wifi_mac_tool.log"


LOG_FILE = get_log_file_path()


def setup_logging():
    LOGGER.setLevel(logging.DEBUG)

    if LOGGER.handlers:
        return

    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    except Exception:
        fallback_log = Path.cwd() / "wifi_mac_tool.log"
        file_handler = logging.FileHandler(fallback_log, encoding="utf-8")

    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)

    LOGGER.info("=" * 80)
    LOGGER.info("MAC Tool started.")
    LOGGER.info(f"Python version: {sys.version}")
    LOGGER.info(f"Platform: {sys.platform}")
    LOGGER.info(f"Script folder: {get_script_folder()}")
    LOGGER.info(f"Script path: {get_script_path()}")
    LOGGER.info(f"Working directory: {Path.cwd()}")
    LOGGER.info(f"Log file: {LOG_FILE}")


def log_exception(message: str):
    LOGGER.error(message)
    LOGGER.error(traceback.format_exc())


def is_admin() -> bool:
    try:
        admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        LOGGER.debug(f"Admin check result: {admin}")
        return admin
    except Exception:
        log_exception("Failed to check admin status.")
        return False


def relaunch_as_admin():
    if sys.platform != "win32":
        return False

    script_path = str(get_script_path())
    args = [script_path] + sys.argv[1:]
    params = subprocess.list2cmdline(args)

    LOGGER.info("Attempting to relaunch as Administrator.")
    LOGGER.info(f"Executable: {sys.executable}")
    LOGGER.info(f"Parameters: {params}")

    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            params,
            str(get_script_folder()),
            1,
        )

        if result <= 32:
            LOGGER.error(f"ShellExecuteW failed with code: {result}")
            return False

        LOGGER.info("Relaunch request sent successfully.")
        return True

    except Exception:
        log_exception("Failed to relaunch as Administrator.")
        return False


def ensure_admin_or_relaunch():
    if is_admin():
        return

    print("Administrator permission is required.")
    print("Opening the Windows administrator prompt...")

    relaunched = relaunch_as_admin()

    if relaunched:
        sys.exit(0)

    print()
    print("Failed to open the administrator prompt.")
    print("Right-click the script or Command Prompt and choose 'Run as administrator'.")
    print(f"Log file: {LOG_FILE}")
    sys.exit(1)


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_powershell(command: str, timeout: int = 60) -> str:
    LOGGER.debug("Running PowerShell command:")
    LOGGER.debug(command.strip())

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    LOGGER.debug(f"PowerShell return code: {result.returncode}")

    if result.stdout.strip():
        LOGGER.debug("PowerShell stdout:")
        LOGGER.debug(result.stdout.strip())

    if result.stderr.strip():
        LOGGER.debug("PowerShell stderr:")
        LOGGER.debug(result.stderr.strip())

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "PowerShell command failed."
        )

    return result.stdout.strip()


def get_net_adapters():
    command = """
    Get-NetAdapter -Physical |
    Select-Object Name, InterfaceDescription, Status, MacAddress, InterfaceGuid |
    ConvertTo-Json -Depth 4
    """

    LOGGER.info("Getting physical network adapters.")

    output = run_powershell(command)

    if not output:
        LOGGER.warning("Get-NetAdapter returned no output.")
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        LOGGER.error("Failed to parse Get-NetAdapter JSON output.")
        LOGGER.error(output)
        raise

    if isinstance(data, dict):
        adapters = [data]
    else:
        adapters = data

    LOGGER.info(f"Detected {len(adapters)} physical adapter(s).")

    for adapter in adapters:
        LOGGER.debug(
            "Adapter detected: "
            f"Name={adapter.get('Name')}, "
            f"Description={adapter.get('InterfaceDescription')}, "
            f"Status={adapter.get('Status')}, "
            f"MAC={adapter.get('MacAddress')}, "
            f"GUID={adapter.get('InterfaceGuid')}"
        )

    return adapters


def is_wifi_adapter(adapter: dict) -> bool:
    text = (
        str(adapter.get("Name", "")) + " " +
        str(adapter.get("InterfaceDescription", ""))
    ).lower()

    wifi_keywords = [
        "wi-fi",
        "wifi",
        "wireless",
        "wlan",
        "802.11",
    ]

    return any(keyword in text for keyword in wifi_keywords)


def is_ethernet_adapter(adapter: dict) -> bool:
    if is_wifi_adapter(adapter):
        return False

    text = (
        str(adapter.get("Name", "")) + " " +
        str(adapter.get("InterfaceDescription", ""))
    ).lower()

    ethernet_keywords = [
        "ethernet",
        "intel(r) ethernet",
        "realtek pcie gbe",
        "realtek gaming",
        "lan",
        "gbe",
        "2.5gbe",
        "i219",
        "i225",
        "i226",
        "killer e",
        "network connection",
    ]

    return any(keyword in text for keyword in ethernet_keywords)


def adapter_matches_type(adapter: dict, adapter_type: str) -> bool:
    if adapter_type == "wifi":
        return is_wifi_adapter(adapter)

    if adapter_type == "ethernet":
        return is_ethernet_adapter(adapter)

    if adapter_type == "all":
        return True

    return False


def adapter_type_label(adapter_type: str) -> str:
    if adapter_type == "wifi":
        return "Wi-Fi"

    if adapter_type == "ethernet":
        return "Ethernet"

    return "Network"


def generate_random_mac() -> str:
    first_byte = random.randint(0x00, 0xFF)

    # Locally administered.
    first_byte |= 0x02

    # Unicast, not multicast.
    first_byte &= 0xFE

    mac_bytes = [first_byte] + [random.randint(0x00, 0xFF) for _ in range(5)]
    mac = "".join(f"{byte:02X}" for byte in mac_bytes)

    LOGGER.info(f"Generated random locally administered MAC: {format_mac(mac)}")

    return mac


def format_mac(mac_12_chars: str) -> str:
    if mac_12_chars is None:
        return "None"

    mac = str(mac_12_chars).replace("-", "").replace(":", "").replace(" ", "").strip()

    if len(mac) != 12:
        return str(mac_12_chars)

    return ":".join(mac[i:i + 2] for i in range(0, 12, 2))


def normalize_mac(mac: str) -> str:
    if mac is None:
        return ""

    return str(mac).replace("-", "").replace(":", "").replace(" ", "").upper()


def find_adapter_registry_key(interface_guid: str):
    clean_guid = str(interface_guid).strip("{}").lower()

    LOGGER.info(f"Searching registry for adapter GUID: {clean_guid}")

    try:
        root = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            NETWORK_CLASS_REG_PATH,
            0,
            winreg.KEY_READ,
        )
    except Exception:
        log_exception("Failed to open network adapter registry class path.")
        return None

    try:
        index = 0

        while True:
            try:
                subkey_name = winreg.EnumKey(root, index)
                index += 1

                subkey_path = NETWORK_CLASS_REG_PATH + "\\" + subkey_name

                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        subkey_path,
                        0,
                        winreg.KEY_READ,
                    ) as subkey:
                        try:
                            value, _ = winreg.QueryValueEx(subkey, "NetCfgInstanceId")
                            registry_guid = str(value).strip("{}").lower()

                            LOGGER.debug(
                                f"Checking registry subkey {subkey_name}: "
                                f"NetCfgInstanceId={registry_guid}"
                            )

                            if registry_guid == clean_guid:
                                LOGGER.info(f"Matched registry key: {subkey_path}")
                                return subkey_path

                        except FileNotFoundError:
                            continue

                except PermissionError:
                    LOGGER.warning(f"Permission denied reading subkey: {subkey_path}")
                    continue

            except OSError:
                break

    finally:
        winreg.CloseKey(root)

    LOGGER.warning(f"No registry key matched adapter GUID: {clean_guid}")
    return None


def get_registry_mac_address(registry_path: str):
    LOGGER.info(f"Reading custom MAC from registry path: {registry_path}")

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            registry_path,
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "NetworkAddress")
            LOGGER.info(f"Registry NetworkAddress value: {format_mac(value)}")
            return str(value)

    except FileNotFoundError:
        LOGGER.info("No custom NetworkAddress registry value found.")
        return None

    except Exception:
        log_exception("Failed to read custom NetworkAddress registry value.")
        return None


def set_mac_address(registry_path: str, mac_12_chars: str):
    LOGGER.info(
        f"Writing custom MAC to registry: {format_mac(mac_12_chars)} "
        f"at {registry_path}"
    )

    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        registry_path,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, "NetworkAddress", 0, winreg.REG_SZ, mac_12_chars)

    LOGGER.info("Registry NetworkAddress value written successfully.")


def remove_custom_mac_address(registry_path: str) -> bool:
    LOGGER.info(f"Removing custom NetworkAddress value from: {registry_path}")

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            registry_path,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, "NetworkAddress")

        LOGGER.info("Custom NetworkAddress registry value removed successfully.")
        return True

    except FileNotFoundError:
        LOGGER.info("No custom NetworkAddress value existed, so there was nothing to remove.")
        return True

    except Exception:
        log_exception("Failed to remove custom NetworkAddress registry value.")
        return False


def restart_adapter(adapter_name: str):
    LOGGER.info(f"Restarting adapter: {adapter_name}")

    print("Restarting adapter...")

    run_powershell(
        f"Disable-NetAdapter -Name {ps_quote(adapter_name)} -Confirm:$false"
    )

    LOGGER.info("Adapter disabled.")
    time.sleep(3)

    run_powershell(
        f"Enable-NetAdapter -Name {ps_quote(adapter_name)} -Confirm:$false"
    )

    LOGGER.info("Adapter enabled.")
    time.sleep(4)


def get_fresh_adapter_by_guid(interface_guid: str):
    LOGGER.info(f"Refreshing adapter info for GUID: {interface_guid}")

    adapters = get_net_adapters()

    for adapter in adapters:
        if str(adapter.get("InterfaceGuid", "")).lower() == str(interface_guid).lower():
            LOGGER.info("Found refreshed adapter info.")
            return adapter

    LOGGER.warning("Could not find refreshed adapter info.")
    return None


def choose_adapter(adapters, adapter_type: str):
    label = adapter_type_label(adapter_type)
    matching_adapters = [
        adapter for adapter in adapters
        if adapter_matches_type(adapter, adapter_type)
    ]

    if not matching_adapters:
        LOGGER.warning(f"No {label} adapter was detected.")

        print(f"No {label} adapter was found.")
        print()
        print("Detected adapters:")

        for index, adapter in enumerate(adapters, start=1):
            print(
                f"{index}. {adapter.get('Name')} - "
                f"{adapter.get('InterfaceDescription')} "
                f"[{adapter.get('Status')}] "
                f"[MAC: {adapter.get('MacAddress')}]"
            )

        return None

    print(f"Detected {label} adapters:")
    print()

    for index, adapter in enumerate(matching_adapters, start=1):
        print(
            f"{index}. {adapter.get('Name')} - "
            f"{adapter.get('InterfaceDescription')} "
            f"[Status: {adapter.get('Status')}] "
            f"[Current MAC: {adapter.get('MacAddress')}]"
        )

    print()

    if len(matching_adapters) == 1:
        LOGGER.info(f"Only one {label} adapter found. Auto-selecting: {matching_adapters[0].get('Name')}")
        return matching_adapters[0]

    while True:
        choice = input(f"Select the {label} adapter number: ").strip()

        if choice.isdigit():
            number = int(choice)

            if 1 <= number <= len(matching_adapters):
                selected = matching_adapters[number - 1]
                LOGGER.info(f"User selected {label} adapter: {selected.get('Name')}")
                return selected

        print("Invalid choice. Try again.")
        LOGGER.warning(f"Invalid adapter selection entered: {choice}")


def print_current_mac(adapter_type: str):
    label = adapter_type_label(adapter_type)

    LOGGER.info(f"Checking current {label} MAC address.")

    adapters = get_net_adapters()

    if not adapters:
        LOGGER.warning("No network adapters found.")
        print("No network adapters were found.")
        return

    matching_adapters = [
        adapter for adapter in adapters
        if adapter_matches_type(adapter, adapter_type)
    ]

    if not matching_adapters:
        LOGGER.warning(f"No {label} adapters found.")
        print(f"No {label} adapters were found.")
        return

    print()
    print(f"Current {label} MAC address:")
    print()

    for adapter in matching_adapters:
        registry_path = find_adapter_registry_key(adapter["InterfaceGuid"])
        custom_mac = None

        if registry_path:
            custom_mac = get_registry_mac_address(registry_path)

        LOGGER.info(
            f"{label} adapter MAC info: "
            f"Name={adapter.get('Name')}, "
            f"Description={adapter.get('InterfaceDescription')}, "
            f"Status={adapter.get('Status')}, "
            f"ActiveMAC={adapter.get('MacAddress')}, "
            f"CustomRegistryMAC={format_mac(custom_mac) if custom_mac else 'None'}"
        )

        print(f"Adapter: {adapter.get('Name')}")
        print(f"Description: {adapter.get('InterfaceDescription')}")
        print(f"Status: {adapter.get('Status')}")
        print(f"Active MAC: {adapter.get('MacAddress')}")

        if custom_mac:
            print(f"Custom registry MAC: {format_mac(custom_mac)}")
        else:
            print("Custom registry MAC: None / default hardware MAC")

        print()


def randomize_adapter_mac(adapter_type: str):
    label = adapter_type_label(adapter_type)

    LOGGER.info(f"Starting {label} MAC randomization.")

    adapters = get_net_adapters()

    if not adapters:
        LOGGER.error("No network adapters were found.")
        print("No network adapters were found.")
        sys.exit(1)

    adapter = choose_adapter(adapters, adapter_type)

    if adapter is None:
        LOGGER.error("No adapter selected.")
        sys.exit(1)

    adapter_name = adapter["Name"]
    interface_guid = adapter["InterfaceGuid"]

    registry_path = find_adapter_registry_key(interface_guid)

    if registry_path is None:
        LOGGER.error("Could not find the registry entry for the selected adapter.")
        print("Could not find the registry entry for this adapter.")
        print(f"Log file: {LOG_FILE}")
        sys.exit(1)

    old_mac = adapter.get("MacAddress")
    old_custom_mac = get_registry_mac_address(registry_path)
    new_mac = generate_random_mac()

    LOGGER.info(f"Selected adapter: {adapter_name}")
    LOGGER.info(f"Interface GUID: {interface_guid}")
    LOGGER.info(f"Old active MAC: {old_mac}")
    LOGGER.info(f"Old custom registry MAC: {format_mac(old_custom_mac) if old_custom_mac else 'None'}")
    LOGGER.info(f"New random MAC: {format_mac(new_mac)}")

    print()
    print(f"Selected adapter: {adapter_name}")
    print(f"Old active MAC: {old_mac}")

    if old_custom_mac:
        print(f"Old custom registry MAC: {format_mac(old_custom_mac)}")
    else:
        print("Old custom registry MAC: None / default hardware MAC")

    print(f"New random MAC: {format_mac(new_mac)}")
    print()

    set_mac_address(registry_path, new_mac)
    restart_adapter(adapter_name)

    fresh_adapter = get_fresh_adapter_by_guid(interface_guid)

    print()
    print("Verification:")
    print()

    if fresh_adapter:
        active_mac = fresh_adapter.get("MacAddress")

        LOGGER.info(f"Verification active MAC: {active_mac}")
        LOGGER.info(f"Verification expected MAC: {format_mac(new_mac)}")

        print(f"Current active MAC: {active_mac}")
        print(f"Expected MAC: {format_mac(new_mac)}")

        if normalize_mac(active_mac) == normalize_mac(new_mac):
            LOGGER.info(f"{label} MAC address changed successfully.")
            print("Result: MAC address changed successfully.")
        else:
            LOGGER.warning(
                "Registry value changed, but active MAC does not match. "
                "Driver may block custom MAC addresses or Windows may need a restart."
            )
            print("Result: The registry value was changed, but the active MAC does not match.")
            print("Your driver may block custom MAC addresses, or Windows may need another restart.")
    else:
        LOGGER.error("Could not re-check the adapter after restarting it.")
        print("Could not re-check the adapter after restarting it.")

    print()
    print(f"Log file: {LOG_FILE}")
    print()


def revert_adapter_mac(adapter_type: str):
    label = adapter_type_label(adapter_type)

    LOGGER.info(f"Starting {label} MAC revert.")

    adapters = get_net_adapters()

    if not adapters:
        LOGGER.error("No network adapters were found.")
        print("No network adapters were found.")
        sys.exit(1)

    adapter = choose_adapter(adapters, adapter_type)

    if adapter is None:
        LOGGER.error("No adapter selected for revert.")
        sys.exit(1)

    adapter_name = adapter["Name"]
    interface_guid = adapter["InterfaceGuid"]

    registry_path = find_adapter_registry_key(interface_guid)

    if registry_path is None:
        LOGGER.error("Could not find the registry entry for the selected adapter during revert.")
        print("Could not find the registry entry for this adapter.")
        print(f"Log file: {LOG_FILE}")
        sys.exit(1)

    old_custom_mac = get_registry_mac_address(registry_path)

    print()
    print(f"Selected adapter: {adapter_name}")
    print(f"Current active MAC: {adapter.get('MacAddress')}")

    if old_custom_mac:
        print(f"Custom registry MAC being removed: {format_mac(old_custom_mac)}")
    else:
        print("No custom registry MAC was found.")

    print()

    removed = remove_custom_mac_address(registry_path)

    if not removed:
        LOGGER.error("Failed to remove the custom MAC registry value.")
        print("Failed to remove the custom MAC registry value.")
        print(f"Log file: {LOG_FILE}")
        sys.exit(1)

    restart_adapter(adapter_name)

    fresh_adapter = get_fresh_adapter_by_guid(interface_guid)

    print()
    print("Verification:")
    print()

    if fresh_adapter:
        active_mac = fresh_adapter.get("MacAddress")

        LOGGER.info(f"Revert verification active MAC: {active_mac}")

        print(f"Current active MAC after revert: {active_mac}")
        print("Result: Revert completed.")
    else:
        LOGGER.error("Could not re-check the adapter after reverting.")
        print("Could not re-check the adapter after reverting.")

    print()
    print(f"Log file: {LOG_FILE}")
    print()


def open_log_file():
    print(f"Log file: {LOG_FILE}")

    try:
        subprocess.Popen(["notepad.exe", str(LOG_FILE)])
    except Exception:
        log_exception("Failed to open log file in Notepad.")
        print("Could not open the log file automatically.")


def show_menu():
    while True:
        print()
        print("MAC Address Tool")
        print("1. Check Wi-Fi MAC")
        print("2. Randomize Wi-Fi MAC")
        print("3. Revert Wi-Fi MAC")
        print("4. Check Ethernet MAC")
        print("5. Randomize Ethernet MAC")
        print("6. Revert Ethernet MAC")
        print("7. Check all physical adapter MACs")
        print("8. Show log file path")
        print("9. Open log file")
        print("10. Exit")
        print()

        choice = input("Choose an option: ").strip()

        LOGGER.info(f"Menu choice selected: {choice}")

        if choice == "1":
            print_current_mac("wifi")
        elif choice == "2":
            randomize_adapter_mac("wifi")
        elif choice == "3":
            revert_adapter_mac("wifi")
        elif choice == "4":
            print_current_mac("ethernet")
        elif choice == "5":
            randomize_adapter_mac("ethernet")
        elif choice == "6":
            revert_adapter_mac("ethernet")
        elif choice == "7":
            print_current_mac("all")
        elif choice == "8":
            print(f"Log file: {LOG_FILE}")
        elif choice == "9":
            open_log_file()
        elif choice == "10":
            LOGGER.info("User exited from menu.")
            break
        else:
            print("Invalid option.")
            LOGGER.warning(f"Invalid menu option: {choice}")


def main():
    if sys.platform != "win32":
        LOGGER.error("This script was run on a non-Windows platform.")
        print("This script is for Windows only.")
        sys.exit(1)

    ensure_admin_or_relaunch()

    parser = argparse.ArgumentParser(
        description="Check, randomize, or revert your Windows Wi-Fi/Ethernet MAC address."
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check the current Wi-Fi MAC address. Same as --check-wifi.",
    )

    parser.add_argument(
        "--randomize",
        action="store_true",
        help="Set a random locally administered MAC address on the Wi-Fi adapter. Same as --randomize-wifi.",
    )

    parser.add_argument(
        "--revert",
        action="store_true",
        help="Remove the custom MAC address from the Wi-Fi adapter. Same as --revert-wifi.",
    )

    parser.add_argument(
        "--check-wifi",
        action="store_true",
        help="Check the current Wi-Fi MAC address.",
    )

    parser.add_argument(
        "--randomize-wifi",
        action="store_true",
        help="Set a random locally administered MAC address on the Wi-Fi adapter.",
    )

    parser.add_argument(
        "--revert-wifi",
        action="store_true",
        help="Remove the custom MAC address from the Wi-Fi adapter.",
    )

    parser.add_argument(
        "--check-ethernet",
        action="store_true",
        help="Check the current Ethernet MAC address.",
    )

    parser.add_argument(
        "--randomize-ethernet",
        action="store_true",
        help="Set a random locally administered MAC address on the Ethernet adapter.",
    )

    parser.add_argument(
        "--revert-ethernet",
        action="store_true",
        help="Remove the custom MAC address from the Ethernet adapter.",
    )

    parser.add_argument(
        "--check-all",
        action="store_true",
        help="Check all physical network adapter MAC addresses.",
    )

    parser.add_argument(
        "--log",
        action="store_true",
        help="Show the log file path.",
    )

    parser.add_argument(
        "--open-log",
        action="store_true",
        help="Open the log file in Notepad.",
    )

    args = parser.parse_args()

    LOGGER.info(f"Arguments: {vars(args)}")

    if args.log:
        print(f"Log file: {LOG_FILE}")
    elif args.open_log:
        open_log_file()
    elif args.check or args.check_wifi:
        print_current_mac("wifi")
    elif args.randomize or args.randomize_wifi:
        randomize_adapter_mac("wifi")
    elif args.revert or args.revert_wifi:
        revert_adapter_mac("wifi")
    elif args.check_ethernet:
        print_current_mac("ethernet")
    elif args.randomize_ethernet:
        randomize_adapter_mac("ethernet")
    elif args.revert_ethernet:
        revert_adapter_mac("ethernet")
    elif args.check_all:
        print_current_mac("all")
    else:
        show_menu()


if __name__ == "__main__":
    setup_logging()

    try:
        main()
        LOGGER.info("MAC Tool finished normally.")
    except KeyboardInterrupt:
        LOGGER.warning("User interrupted the script with Ctrl+C.")
        print()
        print("Cancelled.")
        print(f"Log file: {LOG_FILE}")
    except Exception as error:
        LOGGER.critical("Unhandled error occurred.")
        LOGGER.critical(str(error))
        LOGGER.critical(traceback.format_exc())

        print()
        print("An error occurred.")
        print(str(error))
        print()
        print(f"Log file: {LOG_FILE}")
        print("Open the log file and check the newest error at the bottom.")
        sys.exit(1)
