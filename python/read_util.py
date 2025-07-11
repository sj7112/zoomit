import os
from pathlib import Path
import re
import select
import signal
import sys
import termios
import tty
from typing import Callable, Any

from python.system import (
    clear_input,
    print_prompt_for_raw_mode,
    get_time_out,
    init_time_out,
    safe_backspace,
    toggle_time_out,
)


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.msg_handler import (
    MSG_ERROR,
    MSG_OPER_CANCELLED,
    MSG_OPER_FAIL_BOOL,
    MSG_OPER_FAIL_NUMBER,
    _mf,
    exiterr,
    string,
    warning,
)

# 全局日志配置（放在文件开头）
LOG_FILE = "/var/log/sj_install.log"


def error_handler(response, err_handle=None, error_msg=None):
    """
    Error handler function

    Returns:
        0 = NO ERROR | NOT EXIST: Error handler does not exist
            new_response: The user can return a new response
        2 = CONTINUE: to be continued
        3 = EXIT: to exit the program

    Returns:
        tuple: (error_code, new_response)
    """
    # If no error handler provided, return 0 (no error)
    print(f"response={response}; err_handle={err_handle}; error_msg={error_msg}")
    if not err_handle:
        return 0, response

    # Call the error handler function
    result = err_handle(response, error_msg)
    if isinstance(result, int):
        if result != 0:
            return result, None  # 2 = continue, 3 = exit
        return 0, response  # Must be an integer | string

    rc, new_response = result
    if rc != 0:
        return rc, None  # 2 = continue, 3 = exit
    if new_response is None:
        return 0, response  # Must be an integer | string
    return 0, new_response  # Must be an integer | string


def bool_handler(response: Any) -> Any:
    """Boolean option"""

    if not re.match(r"^[YyNn]$", response):
        string(f"{MSG_OPER_FAIL_BOOL}")
        return 2, None  # 2 = continue
    elif re.match(r"^[Yy]$", response):
        return 0, None
    else:
        return 1, None


def number_handler(response: Any, err_handle: Any, error_msg: str) -> Any:
    """Number option"""
    if isinstance(response, str):
        if not re.match(r"^[0-9]+$", response):
            string(f"{MSG_OPER_FAIL_NUMBER}")
            return 2, None  # continue
        else:
            response = int(response)  # Convert to integer

    return error_handler(response, err_handle, error_msg)


def string_handler(response: Any, err_handle: Any, error_msg: str) -> Any:
    """String option"""

    return error_handler(response, err_handle, error_msg)


def do_confirm_action(prompt: str, option: str, no_value: Any, to_value: Any, err_handle: Any, error_msg: str) -> Any:
    """
    get input response
    """

    def timeout_handler(signum, frame):
        raise TimeoutError

    signal.signal(signal.SIGALRM, timeout_handler)
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    # init_time_out(5) # Testing: Initialize timeout to 5 seconds
    timeout = get_time_out()

    try:
        tty.setraw(fd)
        while True:
            clear_input()
            response = ""
            print_prompt_for_raw_mode(prompt)
            signal.alarm(timeout)

            while True:
                try:
                    # Use select to prevent read() fully blocking
                    ready, _, _ = select.select([sys.stdin], [], [], 0.5)  # 0.5s timeout
                    if ready:
                        ch = sys.stdin.read(1)
                        if not ch:
                            continue

                        # Enter
                        if ch in ["\n", "\r"]:
                            response = response.strip() or no_value  # trim spaces
                            print("\r\n", end="", flush=True)
                            break

                        # Ctrl+C
                        if ch == "\x03":
                            raise KeyboardInterrupt

                        # Ctrl+D (EOF)
                        if ch == "\x04":
                            break

                        # Ctrl+Z
                        if ch == "\x1a":
                            print("Suspending...")
                            os.kill(0, signal.SIGTSTP)  # 0 = current process group

                        # Ctrl+\ (SIGQUIT)
                        if ch == "\x1c":
                            print("Quit signal received...")
                            os.kill(0, signal.SIGQUIT)

                        # Ctrl+X (toggle timeout)
                        if ch == "\x18":
                            timeout = toggle_time_out()
                            signal.alarm(timeout)
                            continue

                        # Backspace
                        if ch in ["\x7f", "\b"]:
                            response = safe_backspace(response)
                            if not response:
                                signal.alarm(timeout)
                            continue

                        # Normal input
                        response += ch
                        signal.alarm(0)  # Reset timeout
                        sys.stdout.write(ch)
                        sys.stdout.flush()

                except TimeoutError:
                    response = to_value  # Use timeout default value
                    print("\r\n", end="", flush=True)
                    break

            # Boolean option [YyNn]
            if option == "bool":
                rc, result = bool_handler(response)

            # Number option
            elif option == "number":
                rc, result = number_handler(response, err_handle, error_msg)

            # String option
            elif option == "string":
                rc, result = string_handler(response, err_handle, error_msg)

            if rc == 2:
                print("\r\n", end="", flush=True)
                continue
            else:
                return rc, result

    except KeyboardInterrupt:
        print("\r\n", end="", flush=True)
        return 130, None

    except Exception as e:
        print(f"\r\n[{MSG_ERROR}]: {e}")
        return 3, None

    finally:
        clear_input()  # Cursor move to the beginning of the line
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)  # restore tty setup
        signal.alarm(0)


def confirm_action(prompt: str, callback: Callable[..., Any] = None, *args: Any, **kwargs: Any) -> Any:
    """
    Confirmation function with callback support

    Args:
        prompt: Prompt message
        callback: Callback function. Returns 0 directly if None
        *args: Positional arguments for callback function
        **kwargs: Can contain cancellation messages and callback function keyword arguments

    Returns:
        0: User confirmed
        1: User cancelled
        2: User interrupt
        3: System Exception
    """

    option = kwargs.pop("option", "bool")  # Default option is bool

    # set default messages if not provided
    msg = kwargs.pop("msg", MSG_OPER_CANCELLED)
    no_msg = kwargs.pop("no_msg", msg)
    error_msg = kwargs.pop("error_msg", msg)
    exit_msg = kwargs.pop("exit_msg", msg)

    # Determine default behavior based on def_val parameter
    if option == "bool":
        yes = kwargs.pop("no_value", True)  # Default: True
        no_value = "Y" if yes else "N"
        prompt = f"{prompt} {'[Y/n]' if yes  else '[y/N]'}"
    elif option == "number":
        no_value = kwargs.pop("no_value", 0)  # Default: 0
    elif option == "string":
        no_value = kwargs.pop("no_value", "")  # Default: blank

    to_value = kwargs.pop("to_value", no_value)  # timeout: default value = no_value
    err_handle = kwargs.pop("err_handle", None)  # default: no error handler

    # Set prompt suffix based on default value
    status, response = do_confirm_action(prompt, option, no_value, to_value, err_handle, error_msg)
    if status == 0:
        if callback:
            if option == "bool":
                return callback(*args)  # 仅返回code
            else:
                return callback(*args, response), response
    elif status == 1:
        warning(no_msg)
    elif status == 2 or status == 3:
        warning(error_msg)
    elif status == 130:
        warning(exit_msg)
    else:
        exiterr(exit_msg)

    if option == "bool":
        return status  # 仅返回code
    else:
        return status, response
