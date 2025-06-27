#!/usr/bin/env python3
import re
import subprocess
import time
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Tuple, Union


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.msg_handler import info
from python.cache.os_info import OSInfo, OSInfoCache

# Global configuration
LOG_FILE = "/var/log/sj_install.log"
DEBUG = False

_os_info: OSInfo = OSInfoCache.get_instance().get()


# ==============================================================================
# (1) Frontend command execution
# ==============================================================================
def cmd_exec(cmd, **kwargs) -> Tuple[bool, Any]:
    """
    Execute a system command and return the result, with optional regex matching.

    Args:
        cmd (str or list): The command to execute, either as a string (e.g., "ls -l")
                           or a list (e.g., ["ls", "-l"]).

    Examples:
        # Get the current user
        user = cmd_exec("whoami")

        # Extract IP address
        ip = cmd_exec("ip -o route get 1")
    """
    # If cmd is a string, convert it to a list using split()
    if isinstance(cmd, str):
        cmd = cmd.split()

    try:
        # Provide default values, allow overriding via kwargs
        run_args = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "text": True,
            "timeout": 300,
        } | kwargs  # Allow user to override defaults

        result = subprocess.run(cmd, **run_args)
        if result.returncode != 0:
            return False, result.stderr
        return True, result  # 原始对象
    except subprocess.TimeoutExpired:
        error_msg = f"[ERROR] 命令执行超时: {' '.join(cmd)}"
        print(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"[ERROR] 命令执行异常: {e}"
        print(error_msg)
        return False, str(e)


def cmd_ex_str(cmd, **kwargs):
    """
    Execute a system command and return the result by string

    Returns:
        str:
            - If the command fails or no pattern match is found, returns an empty string "".
    """
    success, result = cmd_exec(cmd, **kwargs)
    if success:
        return result.stdout  # No regex pattern provided, return full output
    else:
        return ""  # Command failed, return an empty string


def cmd_ex_pat(cmd, pattern, **kwargs):
    """
    Execute a system command and return the result, with optional regex matching.

    Returns:
        str:
            - A regex pattern is provided, returns the first matched group;
            - If the command fails or no pattern match is found, returns an empty string "".

    Examples:
        # Extract IP address
        ip = cmd_ex_pat("ip -o route get 1", r"src (\d+\.\d+\.\d+\.\d+)")
    """
    result = cmd_ex_str(cmd, **kwargs)
    if result:
        match = re.search(pattern, result)
        if match:
            return match.group(1)  # Return the first matched group
    return ""  # No match found, return an empty string


# ==============================================================================
# (2) Backend command execution
# ==============================================================================
def cmd_ex_be(*commands):
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
        # sys.exit(130)  # 128 + 2 (SIGINT)
        return 2

    except Exception as e:
        print(f"\r\033[KError: {e}", file=sys.stderr)
        print()
        return 3


# ==============================================================================
# (3) Package management related command execution
# ==============================================================================
def pm_refresh():
    """package manager refresh"""
    # Define refresh commands for each package manager
    pm_commands = {
        "apt": ["apt-get clean", "apt-get update -q"],
        "yum": ["yum clean all", "yum makecache"],
        "dnf": ["dnf clean all", "dnf makecache"],
        "zypper": ["zypper refresh -f"],
        "pacman": ["pacman -Syy"],
    }
    info("正在刷新缓存...")
    if commands := pm_commands.get(_os_info.package_mgr):
        result = cmd_ex_be(*commands)
        if result == 0:
            info("缓存刷新完成")
        return result


def pm_upgrade():
    """package manager upgrade"""
    # Define upgrade commands for each package manager
    pm_commands = {
        "apt": ["apt-get upgrade -y", "apt-get autoremove -y"],
        "yum": ["yum upgrade -y", "yum autoremove -y"],
        "dnf": ["dnf upgrade -y", "dnf autoremove -y"],
        "zypper": ["zypper update -y"],
        "pacman": ["pacman -Syu --noconfirm"],
    }
    info("正在更新系统...")
    if commands := pm_commands.get(_os_info.package_mgr):
        result = cmd_ex_be(*commands)
        if result == 0:
            info("更新系统完成")
        return result


def pm_install(lnx_cmds: Union[str, List[str]]):
    """package manager install"""
    # Define install commands for each package manager
    pm_commands = {
        "apt": "apt-get install -y",  # Debian, Ubuntu
        "yum": "yum install -y",  # CentOS, RHEL (旧版本)
        "dnf": "dnf install -y",  # Fedora, CentOS 8+, RHEL 8+
        "zypper": "zypper install -y",  # openSUSE
        "pacman": "pacman -Sy --noconfirm",  # Arch Linux, Manjaro
    }
    if isinstance(lnx_cmds, str):
        lnx_cmds = [lnx_cmds]

    info(r"正在安装{}...", " ".join(lnx_cmds))
    if cmd := pm_commands.get(_os_info.package_mgr):
        result = cmd_ex_be(*[f"{cmd} {lnx_cmd}" for lnx_cmd in lnx_cmds])
        if result == 0:
            info(r"安装{}完成", " ".join(lnx_cmds))
        return result


# ==============================================================================
# Main program : Usage examples and tests cmd_ex_be
# ==============================================================================

if __name__ == "__main__":
    DEBUG = os.environ.get("DEBUG") == "1"  # 测试标志

    # Example 1: Execute single command
    print("=== 示例1: 单个命令 ===")
    result = cmd_ex_be("ls -la")
    print(f"命令执行结果: {result}")

    # Example 2: Execute multiple commands
    print("\n=== 示例2: 多个命令 ===")
    result = cmd_ex_be(
        "echo 'Step 1: Starting...'", "sleep 2", "echo 'Step 2: Processing...'", "sleep 1", "echo 'Step 3: Finished!'"
    )
    print(f"命令执行结果: {result}")

    # Example 3: Simulate long running command
    print("\n=== 示例3: 长时间运行 ===")
    result = cmd_ex_be('for i in {1..5}; do echo "Progress: $i/5"; sleep 0.8; done')
    print(f"命令执行结果: {result}")
