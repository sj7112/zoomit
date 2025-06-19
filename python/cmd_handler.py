#!/usr/bin/env python3
import signal
import subprocess
import time
import os
import sys
from datetime import datetime
from pathlib import Path

# Global configuration
LOG_FILE = "/var/log/sj_install.log"
DEBUG = False


def cmd_exec(*commands):
    """
    Execute multiple commands connected with &&
    Args: *commands - list of commands to execute
    Returns: int - 0 for success, non-zero for failure
    """
    if not commands:
        return 1

    # Combine commands with &&
    combined_cmd = " && ".join(commands)

    # Remove extra spaces
    combined_cmd = " ".join(combined_cmd.split())

    # Add parentheses for command groups
    if "&&" in combined_cmd:
        combined_cmd = f"({combined_cmd})"

    # Execute command (non-quiet mode)
    print(f"执行: {combined_cmd} ... ", file=sys.stderr)

    # Execute command & monitor progress
    return monitor_progress(combined_cmd, LOG_FILE)


def monitor_progress(cmd, log_file=None):
    """
    Monitor command progress and display updates in single line
    Args:
        cmd - command to execute
        log_file - log file path, defaults to global LOG_FILE
    Returns: int - command execution result
    """
    if log_file is None:
        log_file = LOG_FILE

    process = None

    try:
        # Ensure log file directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Start command process
        with open(log_file, "a", encoding="utf-8") as log_f:
            process = subprocess.Popen(cmd, shell=True, stdout=log_f, stderr=subprocess.STDOUT, text=True)

        # Check if PID is valid
        if process.pid is None:
            print("Error: Empty PID", file=sys.stderr)
            return 1

        # DEBUG mode skips process detection
        if not DEBUG and process.poll() is not None:
            print(f"Error: Invalid PID {process.pid}")
            return process.returncode or 1

        print(f"Monitoring process {process.pid}...")

        # Get terminal width
        try:
            max_width = min(os.get_terminal_size().columns, 80)
        except OSError:
            max_width = 80

        # Monitoring variables
        spinner = "|/-\\"
        spin_index = 0
        last_size = 0
        latest = ""

        # Monitoring loop
        while process.poll() is None:
            time.sleep(0.2)

            # Check log file updates
            if os.path.exists(log_file):
                try:
                    current_size = os.path.getsize(log_file)
                    if current_size != last_size:
                        # Extract last valid line, clean control characters
                        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                            lines = f.readlines()
                            if lines:
                                # Clean control characters and truncate to max width
                                latest = "".join(
                                    char for char in lines[-1].strip() if ord(char) >= 32 or char in "\t\n"
                                )
                                latest = latest[:max_width]
                        last_size = current_size
                except (OSError, IOError):
                    pass

            # Always refresh spinner + latest
            spin_index = (spin_index + 1) % 4
            display_text = latest if latest else "Waiting..."
            print(f"\r\033[K[{spinner[spin_index]}] {display_text}", end="", flush=True)

        # Wait for process to end and get return code
        return_code = process.wait()

        # Display final status
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\r\033[K[-] 完成 Completed: {current_time}")
        print()  # New line

        return return_code

    except KeyboardInterrupt:
        if process and process.poll() is None:
            print("\n检测到 Ctrl+C，正在终止后台子进程...", file=sys.stderr)
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        print("脚本已中断并清理子进程。")
        sys.exit(130)  # 128 + 2 (SIGINT)

    except Exception as e:
        print(f"\r\033[KError: {e}", file=sys.stderr)
        print()
        return 1


# Usage examples and tests
if __name__ == "__main__":
    DEBUG = os.environ.get("DEBUG") == "1"  # 测试标志

    # Example 1: Execute single command
    print("=== 示例1: 单个命令 ===")
    result = cmd_exec("ls -la")
    print(f"命令执行结果: {result}")

    # Example 2: Execute multiple commands
    print("\n=== 示例2: 多个命令 ===")
    result = cmd_exec(
        "echo 'Step 1: Starting...'", "sleep 2", "echo 'Step 2: Processing...'", "sleep 1", "echo 'Step 3: Finished!'"
    )
    print(f"命令执行结果: {result}")

    # Example 3: Simulate long running command
    print("\n=== 示例3: 长时间运行 ===")
    result = cmd_exec('for i in {1..5}; do echo "Progress: $i/5"; sleep 0.8; done')
    print(f"命令执行结果: {result}")
