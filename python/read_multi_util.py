from pathlib import Path
import re
import sys


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.msg_handler import MSG_OPER_CANCELLED, _mf, string, warning


# ==============================================================================
# 提供交互式多选界面，供用户选择要启用的基础设施组件
# 输出：
#   SELECTED - 关联数组，存储用户选择的组件状态
# 使用示例：
#   用户可输入：1 4 5（空格分隔的编号）
# ==============================================================================
# multi-selection interface to select infrastructure components to enable
# Output:
#   SELECTED - the selection status of user-chosen components
# Usage example:
#   User input: 1 4 5 (space-separated component numbers)
# ==============================================================================
def print_options(options, per_line=3):
    """Print options list"""
    maxlen = max(len(opt) for opt in options)
    for i, opt in enumerate(options):
        print(f"{i + 1:2d}) {opt.ljust(maxlen)}", end="   ")
        if (i + 1) % per_line == 0 or i + 1 == len(options):
            print()


def print_tips():
    """Print operation tips"""
    str = _mf(
        "Multiple choice format like 1 2 3; selecting the same item again will deselect it; press Enter to finish"
    )
    print(f"\n\033[44m {str} \033[0m\n")


def print_current_selection(selected):
    """Print current selection status"""
    selection = " ".join(selected) if selected else _mf("None")
    print(f"– {_mf('Current selection')}: {selection}\n")


def toggle_selection(options, selected, indexes):
    """Toggle selection status"""
    new_selected = []
    added = []
    removed = []
    for i, opt in enumerate(options):
        idx = i + 1
        if idx in indexes:
            if opt not in selected:
                new_selected.append(opt)
                added.append(opt)  # add opt
            else:
                removed.append(opt)  # remove opt
        else:
            if opt in selected:
                new_selected.append(opt)  # retain opt

    if added:
        print(f"✔ {_mf('Current selection')}: {' '.join(added)}")
    if removed:
        print(f"✘ {_mf('Deselected')}: {' '.join(removed)}")

    print_current_selection(new_selected)
    return new_selected


def multiple_selector(options, selected, per_line=1):
    """Multi-selection interactive interface"""
    print_options(options, per_line)
    print_tips()
    print_current_selection(selected)

    while True:
        try:
            user_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            warning(MSG_OPER_CANCELLED)
            break

        if not user_input:
            break

        if not re.match(r"^[0-9 ]+$", user_input):
            string(r"✘ Please enter a valid number (1-{})", len(options))
            continue

        choices = user_input.split()
        choice_int = []
        choice_err = []
        for choice in choices:
            num = int(choice)
            choice_int.append(num)
            if not (0 < num <= len(options)):
                choice_err.append(choice)

        if choice_err:
            string(r"✘ Invalid number: {}", " ".join(choice_err))
            continue

        selected = toggle_selection(options, selected, choice_int)

    return selected
