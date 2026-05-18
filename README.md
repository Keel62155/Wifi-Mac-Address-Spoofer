# MAC Address Changer Tool

A Windows Python tool for checking, randomizing, and reverting Wi-Fi or Ethernet MAC addresses.

This tool is designed for personal privacy testing, adapter troubleshooting, and local network testing on devices and networks you own or are authorized to use.

## Features

- Check current Wi-Fi MAC address
- Check current Ethernet MAC address
- Check all physical network adapter MAC addresses
- Randomize Wi-Fi MAC address
- Randomize Ethernet MAC address
- Revert Wi-Fi MAC address back to default behavior
- Revert Ethernet MAC address back to default behavior
- Automatically asks for administrator permissions
- Creates a log file in the same folder as the script
- Opens the log file directly in Notepad
- Verifies whether the active MAC changed after restarting the adapter

## Requirements

- Windows 10 or Windows 11
- Python 3.10+
- Administrator permissions

No external Python packages are required.

## Important Notes

Not every network adapter supports MAC address changes.

Some Wi-Fi adapters, especially certain Realtek Wi-Fi cards, may ignore custom registry MAC addresses even when the registry value is changed successfully. Ethernet adapters usually support MAC changes more often, but it still depends on the driver.

This tool does not bypass bans, licensing systems, anti-cheat systems, school/work restrictions, or router/device restrictions. Use it only on your own device and networks where you have permission.

## Installation

1. Download or clone this repository.
2. Make sure Python is installed.
3. Run the script:

```bash
python "Mac Address Changer.py"
