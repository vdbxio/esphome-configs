# UPLOAD.PY - V24.09 - WIP
# Script to batch upload firmware
# $
# python3 upload.py file.yaml
# $
# Written with claude.ai
# TODO: 
# - Progress bars?
# - Improve confirmation messages
# - Processes fail a few times in the beginning, but seem to complete
# - Clean up output


import os
import subprocess
import serial.tools.list_ports
import argparse
import re
import concurrent.futures
import time

def get_connected_boards():
    all_ports = list(serial.tools.list_ports.comports())
    esp_ports = []
    
    for port in all_ports:
        if "Bluetooth-Incoming-Port" not in port.device:
            if "CH340" in port.description or "CP210x" in port.description:
                esp_ports.append(port.device)
            elif not re.search(r"(AMA|ACM|Bluetooth|IrDA)", port.device, re.IGNORECASE):
                esp_ports.append(port.device)
    
    return esp_ports

def check_esphome_config(yaml_path):
    command = f"esphome config {yaml_path}"
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def upload_firmware(port, yaml_path, skip_update, max_retries=3):
    
    command = f"esphome upload --device {port} {yaml_path}"
    for attempt in range(max_retries):
        try:
            result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
            print(f"Firmware uploaded successfully to {port}")
            return True, port, result.stdout
        except subprocess.CalledProcessError as e:
            print(f"Attempt {attempt + 1} failed for {port}: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying upload to {port} in 5 seconds...")
                time.sleep(5)
            else:
                print(f"All attempts failed for {port}. Last error: {e.stderr}")
                return False, port, e.stderr

def main():
    parser = argparse.ArgumentParser(description="Upload ESPHome firmware to connected boards in parallel.")
    parser.add_argument("yaml_path", help="Path to the ESPHome YAML configuration file")
    parser.add_argument("--skip-update", action="store_true", help="Skip ESPHome update step")
    args = parser.parse_args()

    yaml_path = args.yaml_path
    if not os.path.exists(yaml_path):
        print("YAML file not found. Please check the path and try again.")
        return

    print("Checking ESPHome configuration...")
    config_valid, config_output = check_esphome_config(yaml_path)
    if not config_valid:
        print("ESPHome configuration check failed:")
        print(config_output)
        return

    boards = get_connected_boards()
    if not boards:
        print("No compatible development boards found. Please connect a board and try again.")
        return

    print(f"Found {len(boards)} compatible board(s):")
    for i, board in enumerate(boards, 1):
        print(f"{i}. {board}")

    confirm = input("Do you want to upload the firmware to all these boards in parallel? (y/n): ")
    if confirm.lower() != 'y':
        print("Upload cancelled.")
        return

    print("Starting parallel uploads...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(boards)) as executor:
        future_to_board = {executor.submit(upload_firmware, board, yaml_path, args.skip_update): board for board in boards}
        for future in concurrent.futures.as_completed(future_to_board):
            board = future_to_board[future]
            try:
                success, port, output = future.result()
                if success:
                    print(f"Upload completed successfully for {port}")
                    print("Output:")
                    print(output)
                else:
                    print(f"Upload failed for {port} after all retry attempts.")
                    print("Error output:")
                    print(output)
            except Exception as exc:
                print(f"Upload for {board} generated an exception: {exc}")

    print("All uploads completed.")

if __name__ == "__main__":
    main()
