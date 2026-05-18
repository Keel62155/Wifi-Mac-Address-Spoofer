import winreg
import subprocess
import os
import sys
import uuid
import random
import string
import json
import ctypes
from datetime import datetime

BACKUP_FILE = "hwid_backup.json"

def is_admin():
    try:
        return os.getuid() == 0
    except AttributeError:
        return ctypes.windll.shell32.IsUserAnAdmin()

def run_as_admin():
    """Restart the script with admin privileges"""
    if is_admin():
        return True
    
    print("[*] Requesting Administrator privileges...")
    
    try:
        # Get the script path and arguments
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        
        # Use ShellExecute to run as admin
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,  # Parent window
            "runas",  # Verb - requests elevation
            sys.executable,  # Program (python.exe)
            f'"{script}" {params}',  # Parameters
            None,  # Working directory
            1  # Show window (SW_SHOWNORMAL)
        )
        
        # ShellExecute returns > 32 if successful
        if ret > 32:
            sys.exit(0)  # Exit this non-elevated instance
        else:
            print(f"[-] Failed to elevate. Error code: {ret}")
            return False
            
    except Exception as e:
        print(f"[-] Elevation failed: {e}")
        print("[-] Please manually run as Administrator")
        input("Press Enter to exit...")
        return False

def get_current_values():
    """Retrieve all current HWID-related values"""
    values = {}
    
    # MachineGuid
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        )
        values["MachineGuid"] = winreg.QueryValueEx(key, "MachineGuid")[0]
        winreg.CloseKey(key)
    except:
        values["MachineGuid"] = "ERROR_READING"
    
    # HwProfileGuid
    try:
        key_path = r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ)
        values["HwProfileGuid"] = winreg.QueryValueEx(key, "HwProfileGuid")[0]
        winreg.CloseKey(key)
    except:
        values["HwProfileGuid"] = "ERROR_READING"
    
    # ProductId
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        )
        values["ProductId"] = winreg.QueryValueEx(key, "ProductId")[0]
        winreg.CloseKey(key)
    except:
        values["ProductId"] = "ERROR_READING"
    
    # MachineName (Computer Name)
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName",
            0, winreg.KEY_READ
        )
        values["ComputerName"] = winreg.QueryValueEx(key, "ComputerName")[0]
        winreg.CloseKey(key)
    except:
        values["ComputerName"] = "ERROR_READING"
    
    # MAC Addresses
    try:
        result = subprocess.run(
            ["wmic", "nic", "where", "NetConnectionStatus=2", "get", "MACAddress,Name", "/value"],
            capture_output=True, text=True
        )
        values["MAC_Addresses"] = []
        lines = result.stdout.strip().split('\n')
        current_mac = {}
        for line in lines:
            if '=' in line:
                key_val = line.strip().split('=', 1)
                if len(key_val) == 2:
                    k, v = key_val
                    if k == "MACAddress" and v:
                        current_mac["mac"] = v
                    elif k == "Name":
                        current_mac["name"] = v
                        if "mac" in current_mac:
                            values["MAC_Addresses"].append(current_mac)
                            current_mac = {}
    except:
        values["MAC_Addresses"] = []
    
    # Disk Serials
    try:
        result = subprocess.run(
            ["wmic", "diskdrive", "get", "Model,SerialNumber", "/value"],
            capture_output=True, text=True
        )
        values["Disk_Serials"] = []
        lines = result.stdout.strip().split('\n\n')
        for block in lines:
            model = ""
            serial = ""
            for line in block.split('\n'):
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    if k == "Model":
                        model = v
                    elif k == "SerialNumber":
                        serial = v
            if model or serial:
                values["Disk_Serials"].append({"model": model, "serial": serial})
    except:
        values["Disk_Serials"] = []
    
    values["timestamp"] = datetime.now().isoformat()
    return values

def save_backup(values):
    """Save current values to backup file"""
    try:
        with open(BACKUP_FILE, 'w') as f:
            json.dump(values, f, indent=2)
        return True
    except Exception as e:
        print(f"[-] Failed to save backup: {e}")
        return False

def load_backup():
    """Load backup from file"""
    try:
        if os.path.exists(BACKUP_FILE):
            with open(BACKUP_FILE, 'r') as f:
                return json.load(f)
        return None
    except Exception as e:
        print(f"[-] Failed to load backup: {e}")
        return None

def display_current_values(values=None):
    """Display current HWID values"""
    if values is None:
        values = get_current_values()
    
    print("\n" + "="*60)
    print("CURRENT HARDWARE IDENTIFIERS")
    print("="*60)
    print(f"MachineGuid:     {values.get('MachineGuid', 'N/A')}")
    print(f"HwProfileGuid:   {values.get('HwProfileGuid', 'N/A')}")
    print(f"ProductId:       {values.get('ProductId', 'N/A')}")
    print(f"ComputerName:    {values.get('ComputerName', 'N/A')}")
    print(f"Timestamp:       {values.get('timestamp', 'N/A')}")
    
    print("\nNetwork Adapters (MAC Addresses):")
    macs = values.get('MAC_Addresses', [])
    if macs:
        for adapter in macs:
            print(f"  [{adapter.get('name', 'Unknown')[:40]}]")
            print(f"    MAC: {adapter.get('mac', 'N/A')}")
    else:
        print("  None found or error reading")
    
    print("\nDisk Drives:")
    disks = values.get('Disk_Serials', [])
    if disks:
        for disk in disks:
            print(f"  Model:  {disk.get('model', 'Unknown')}")
            print(f"  Serial: {disk.get('serial', 'N/A')}")
    else:
        print("  None found or error reading")
    
    print("="*60 + "\n")

def revert_changes():
    """Restore original values from backup"""
    backup = load_backup()
    
    if not backup:
        print("[-] No backup file found. Cannot revert.")
        return False
    
    print("[*] Reverting to backed up values...")
    success = True
    
    # Restore MachineGuid
    if "MachineGuid" in backup:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0, 
                winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
            )
            winreg.SetValueEx(key, "MachineGuid", 0, winreg.REG_SZ, backup["MachineGuid"])
            winreg.CloseKey(key)
            print(f"[+] Restored MachineGuid: {backup['MachineGuid']}")
        except Exception as e:
            print(f"[-] Failed to restore MachineGuid: {e}")
            success = False
    
    # Restore HwProfileGuid
    if "HwProfileGuid" in backup:
        try:
            key_path = r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001"
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "HwProfileGuid", 0, winreg.REG_SZ, backup["HwProfileGuid"])
            winreg.CloseKey(key)
            print(f"[+] Restored HwProfileGuid: {backup['HwProfileGuid']}")
        except Exception as e:
            print(f"[-] Failed to restore HwProfileGuid: {e}")
            success = False
    
    # Restore ProductId
    if "ProductId" in backup:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
                0, 
                winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
            )
            winreg.SetValueEx(key, "ProductId", 0, winreg.REG_SZ, backup["ProductId"])
            winreg.CloseKey(key)
            print(f"[+] Restored ProductId: {backup['ProductId']}")
        except Exception as e:
            print(f"[-] Failed to restore ProductId: {e}")
            success = False
    
    # Restore ComputerName
    if "ComputerName" in backup:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "ComputerName", 0, winreg.REG_SZ, backup["ComputerName"])
            winreg.CloseKey(key)
            print(f"[+] Restored ComputerName: {backup['ComputerName']}")
        except Exception as e:
            print(f"[-] Failed to restore ComputerName: {e}")
            success = False
    
    if success:
        print("\n[+] Revert completed successfully!")
        print("[!] System reboot required for changes to take effect.")
    else:
        print("\n[-] Some values failed to revert. Check errors above.")
    
    return success

def generate_random_guid():
    return str(uuid.uuid4())

def generate_random_product_id():
    chars = string.ascii_uppercase + string.digits
    return '-'.join(''.join(random.choices(chars, k=5)) for _ in range(4))

def spoof_values():
    """Spoof all registry-based identifiers"""
    print("\n[*] Checking current values and creating backup...")
    current = get_current_values()
    display_current_values(current)
    
    confirm = input("Create backup and proceed with spoofing? (yes/no): ").lower()
    if confirm != "yes":
        print("[-] Cancelled.")
        return
    
    if not save_backup(current):
        print("[-] Backup failed. Aborting for safety.")
        return
    
    print("[*] Applying spoofed values...")
    
    # Spoof MachineGuid
    try:
        new_guid = generate_random_guid()
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0, 
            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
        )
        winreg.SetValueEx(key, "MachineGuid", 0, winreg.REG_SZ, new_guid)
        winreg.CloseKey(key)
        print(f"[+] MachineGuid -> {new_guid}")
    except Exception as e:
        print(f"[-] MachineGuid failed: {e}")
    
    # Spoof HwProfileGuid
    try:
        new_guid = generate_random_guid()
        key_path = r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "HwProfileGuid", 0, winreg.REG_SZ, new_guid)
        winreg.CloseKey(key)
        print(f"[+] HwProfileGuid -> {new_guid}")
    except Exception as e:
        print(f"[-] HwProfileGuid failed: {e}")
    
    # Spoof ProductId
    try:
        new_id = generate_random_product_id()
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            0, 
            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
        )
        winreg.SetValueEx(key, "ProductId", 0, winreg.REG_SZ, new_id)
        winreg.CloseKey(key)
        print(f"[+] ProductId -> {new_id}")
    except Exception as e:
        print(f"[-] ProductId failed: {e}")
    
    # Spoof ComputerName
    try:
        new_name = "DESKTOP-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "ComputerName", 0, winreg.REG_SZ, new_name)
        winreg.CloseKey(key)
        print(f"[+] ComputerName -> {new_name}")
    except Exception as e:
        print(f"[-] ComputerName failed: {e}")
    
    print("\n[+] Spoofing completed!")
    print("[!] REBOOT REQUIRED for changes to take effect.")
    print(f"[!] Backup saved to: {os.path.abspath(BACKUP_FILE)}")

def main():
    # Check for admin and auto-elevate if needed
    if not is_admin():
        run_as_admin()
        # If we get here, elevation failed
        sys.exit(1)
    
    print("[+] Running with Administrator privileges")
    
    while True:
        print("\n" + "="*40)
        print("HWID SPOOFER & RESTORE TOOL")
        print("="*40)
        print("1. Check current HWID values")
        print("2. Spoof HWID (with auto-backup)")
        print("3. Revert to original values")
        print("4. View backup file contents")
        print("5. Exit")
        print("="*40)
        
        choice = input("Select option (1-5): ").strip()
        
        if choice == "1":
            current = get_current_values()
            display_current_values(current)
            input("Press Enter to continue...")
            
        elif choice == "2":
            spoof_values()
            input("Press Enter to continue...")
            
        elif choice == "3":
            revert_changes()
            input("Press Enter to continue...")
            
        elif choice == "4":
            backup = load_backup()
            if backup:
                print("\n[*] Backup file contents:")
                display_current_values(backup)
            else:
                print("[-] No backup file found.")
            input("Press Enter to continue...")
            
        elif choice == "5":
            print("[*] Exiting...")
            break
        else:
            print("[-] Invalid option")

if __name__ == "__main__":
    main()