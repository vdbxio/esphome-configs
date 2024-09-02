# USBMON.PY - V24.09 - WIP
# Script to monitor USB serial devices and monitor stability
# Designed to investigate hardware issues
# $
# python3 usbmon.py
# $
# Written with chatGPT



import os
import time
import re
import signal
import sys

# Initialize device tracking
current_devices = set()
previous_devices = set()
disconnect_counts = {}

# Flag to indicate if the script should run or exit
running = True

# Function to handle termination signals
def signal_handler(sig, frame):
    global running
    print("\nExiting...")
    running = False

# Register signal handlers for graceful exit
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Function to get list of current devices
def get_current_devices():
    devices = set()
    try:
        # List devices matching the pattern
        for device in os.listdir('/dev'):
            if device.startswith('cu.usbmodem'):
                devices.add(os.path.join('/dev', device))
    except FileNotFoundError:
        pass
    return devices

# Function to update device state
def update_devices():
    global previous_devices
    global current_devices
    global disconnect_counts

    new_devices = get_current_devices()

    # Track disconnections
    for prev_device in previous_devices:
        if prev_device not in new_devices:
            base_device = re.sub(r'\W', '_', os.path.basename(prev_device))
            if base_device in disconnect_counts:
                disconnect_counts[base_device] += 1
            else:
                disconnect_counts[base_device] = 1

    # Update previous_devices to the current state
    previous_devices = new_devices
    current_devices = new_devices

# Function to display the current devices and their disconnection counts
def display_devices():
    print("Active /dev/cu.usbmodem* devices:")
    # Sort devices numerically
    sorted_devices = sorted(current_devices, key=lambda x: int(re.search(r'\d+', os.path.basename(x)).group()))
    for device in sorted_devices:
        base_device = re.sub(r'\W', '_', os.path.basename(device))
        count = disconnect_counts.get(base_device, 0)
        print(f"{device} (Disconnections: {count})")

def main():
    global running
    while running:
        os.system('clear')  # Clear the screen
        update_devices()
        display_devices()
        time.sleep(0.1)  # Adjusted sleep interval

if __name__ == "__main__":
    main()
