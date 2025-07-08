import os
from pathlib import Path
import re
import signal
import sys
from typing import Callable, Any


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.msg_handler import MSG_ERROR, _mf, exiterr, string, warning

# 全局日志配置（放在文件开头）
LOG_FILE = "/var/log/sj_install.log"
CONF_TIME_OUT = os.environ.get("CONF_TIME_OUT", 0)  # 0=永不超时


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
        if err_handle:
            err_code = err_handle(response, error_msg)
            if err_code != 0:
                return err_code, None  # 2 = continue, 3 = exit
        elif not re.match(r"^[0-9]+$", response):
            string(r"[{}] Invalid input! Please enter a number", MSG_ERROR)
            return 2, None  # continue
        return 0, int(response)

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

    # Set the signal handler and a timeout of 10 seconds
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(CONF_TIME_OUT)

    try:
        # Set prompt suffix based on default value
        while True:
            response = input(f"{prompt} ").strip().lower()
            signal.alarm(0)  # Cancel the alarm if input is successful
            if response == "":
                response = no_value

            status, response = action_handler(response, option, err_handle, error_msg)
            if status == 2:
                print()
                continue  # Continue to prompt again
            else:
                return status, response

    except KeyboardInterrupt:
        return 130, None  # 130 = 128 + 2 (SIGINT)
    except TimeoutError:  # 142 = 128 + 14 (SIGALRM)
        print()
        response = to_value
        status, response = action_handler(response, option, err_handle, error_msg)
        return status, response
    except Exception as e:
        print()
        string(r"Input processing error: {}", e)
        return 3, None


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
    msg = kwargs.pop("msg", _mf("Operation cancelled"))
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
                return callback(*args), None
            else:
                return callback(*args, response), response
    elif status == 1:
        warning(no_msg)
    elif status == 2 or status == 3:
        string(error_msg)
    elif status == 130:
        print()
        string(exit_msg)
    else:
        print()
        exiterr(exit_msg)

    return status, response
