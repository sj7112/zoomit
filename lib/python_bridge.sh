#!/bin/bash

# Load once only
if [[ -z "${LOADED_PYTHON_BRIDGE:-}" ]]; then
  LOADED_PYTHON_BRIDGE=1

  # Declare global
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # bin direcotry
  : "${PYTHON_DIR:=$(dirname "$BIN_DIR")/python}"               # python directory

  # python3虚拟环境（区分是否需要 sudo 包装）
  # PYTHON="$HOME/.venv/bin/python"
  py_exec() {
    if [ -n "$SUDO_CMD" ]; then
      env LANG="$LANG" LANGUAGE="$LANGUAGE" "$SUDO_CMD" "$HOME/.venv/bin/python" "$@"
    else
      env LANG="$LANG" LANGUAGE="$LANGUAGE" "$HOME/.venv/bin/python" "$@"
    fi
  }

  # ===== 调用 myshell.py 中的命令 =====
  sh_update_source() {
    py_exec "$PYTHON_DIR/myshell.py" sh_update_source "$DISTRO_OSTYPE"
  }

  # User interaction, cannot use subshells like $(...), use configuration file to pass data
  sh_fix_ip() {
    py_exec "$PYTHON_DIR/myshell.py" sh_fix_ip
  }

  sh_clear_cache() {
    py_exec "$PYTHON_DIR/myshell.py" sh_clear_cache
  }

  # ===== 调用 mypip.py 中的命令 =====
  sh_install_pip() {
    py_exec "$PYTHON_DIR/mypip.py"
  }

  # ===== 从ast_parser.py导入的函数 =====
  parse_code_files() {
    local sh_file="$1"

    # 直接输出处理结果
    python3 -c "
import sys
sys.path.append('$PYTHON_DIR')
from lang_util import parse_code_files

for item in parse_code_files('$sh_file'):
    print(item)
"
  }

fi
