from pathlib import Path
import re
import signal
import sys
import termios
import tty
from typing import Callable, Any

from python.system import (
    clear_input,
    format_prompt_for_raw_mode,
    get_time_out,
    safe_backspace,
    show_ctrl_t_feedback,
    toggle_time_out,
)


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.msg_handler import MSG_ERROR, MSG_OPER_CANCELLED, _mf, exiterr, string, warning

# 全局日志配置（放在文件开头）
LOG_FILE = "/var/log/sj_install.log"
CONF_TIME_OUT = get_time_out()  # 0=永不超时


def action_handler(response: Any, option: str, err_handle: Any, error_msg: str) -> Any:
    """
    get status and response
    """
    # Boolean option
    if option == "bool":
        if not re.match(r"^[YyNn]$", response):
            if err_handle:
                return err_handle(response, error_msg), None  # 2 = continue, 3 = exit
            else:
                string("Please enter 'y' for yes, 'n' for no, or press Enter for default")
                return 2, None  # 2 = continue
        elif re.match(r"^[Yy]$", response):
            return 0, None
        else:
            return 1, None

    # Number option
    elif option == "number":
        if isinstance(response, str):
            if not re.match(r"^[0-9]+$", response):
                string("Invalid input! Please enter a number")
                return 2, None  # continue
            else:
                response = int(response)  # Convert to integer
        if err_handle:
            err_code = err_handle(response, error_msg)
            if err_code != 0:
                return err_code, None  # 2 = continue, 3 = exit
        return 0, response  # Must be an integer

        # String option
    elif option == "string":
        if err_handle:
            err_code = err_handle(response, error_msg)
            if err_code != 0:
                return err_code, None  # 2 = continue, 3 = exit
        return 0, response


def do_confirm_action(prompt: str, option: str, no_value: Any, to_value: Any, err_handle: Any, error_msg: str) -> Any:
    """
    get input response
    """

    def timeout_handler(signum, frame):
        raise TimeoutError

    signal.signal(signal.SIGALRM, timeout_handler)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)
        while True:
            clear_input()
            response = ""
            timeout = get_time_out()
            prompt = format_prompt_for_raw_mode(prompt)
            print(f"{prompt} ", end="", flush=True)
            signal.alarm(timeout)

            while True:
                try:
                    ch = sys.stdin.read(1)
                except KeyboardInterrupt:
                    raise
                except Exception:
                    continue

                if not ch:
                    continue

                # Enter
                if ch in ["\n", "\r"]:
                    print("\r\n", end="", flush=True)
                    break

                # Ctrl+C
                if ch == "\x03":
                    raise KeyboardInterrupt

                # Ctrl+D (EOF)
                if ch == "\x04":
                    return 1, None

                # Ctrl+X (toggle timeout)
                if ch == "\x18":
                    timeout = toggle_time_out()
                    show_ctrl_t_feedback()
                    continue

                # Backspace
                if ch in ["\x7f", "\b"]:
                    response = safe_backspace(response)
                    continue

                # Normal input
                response += ch
                sys.stdout.write(ch)
                sys.stdout.flush()

            response = response.strip() or no_value  # trim spaces

            status, result = action_handler(response, option, err_handle, error_msg)
            if status == 2:
                print("\r\n", end="", flush=True)
                continue
            else:
                return status, result

    except KeyboardInterrupt:
        print("\r\n", end="", flush=True)
        return 130, None
    except TimeoutError:
        print("\r\n", end="", flush=True)
        status, result = action_handler(to_value, option, err_handle, error_msg)
        return status, result
    except Exception as e:
        print(f"\r\n[Input error]: {e}")
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
    err_handle = kwargs.pop("err_handle", "")  # default: no error handler

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
