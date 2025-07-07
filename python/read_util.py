from pathlib import Path
import sys
from typing import Callable, Any


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.msg_handler import _mf, string, warning

# 全局日志配置（放在文件开头）
LOG_FILE = "/var/log/sj_install.log"


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

    try:
        # Priority: nomsg > msg > default value
        no_msg = kwargs.pop("nomsg", kwargs.pop("msg", _mf("Operation cancelled")))
        # Priority: errmsg > msg > default value
        err_msg = kwargs.pop("errmsg", kwargs.pop("msg", _mf("Invalid input. Please enter Y or N")))

        # Get default and exit parameters
        default = kwargs.pop("default", True)  # default value = Y
        exit = kwargs.pop("exit", True)  # default = exit immediately

        # Set prompt suffix based on default value
        if default:
            prompt_suffix = "[Y/n]"
            default_choice = "y"
        else:
            prompt_suffix = "[y/N]"
            default_choice = "n"

        while True:
            response = input(f"{prompt} {prompt_suffix} ").strip().lower()
            if response == "":
                response = default_choice

            if response in ("y", "yes"):
                if callback:
                    return callback(*args)  # Execute callback function
                return 0
            elif response in ("n", "no"):
                warning(no_msg)  # Output message for 'no' choice
                return 1
            else:
                print(err_msg)  # Output error message
                if not exit:
                    continue  # Continue loop without returning
                return 2

    except KeyboardInterrupt:
        print()
        string("Operation cancelled")
        return 2
    except Exception as e:
        string(r"Input processing error: {}", e)
        return 3
