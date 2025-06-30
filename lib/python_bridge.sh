#!/bin/bash

# Load once only
if [[ -z "${LOADED_PYTHON_BRIDGE:-}" ]]; then
  LOADED_PYTHON_BRIDGE=1

  # Declare global
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # bin direcotry
  : "${ROOT_DIR:=$(dirname "$BIN_DIR")}"                        # project root directory
  : VENV_BIN="$HOME/.venv/bin/python"

  # python3虚拟环境（区分是否需要 sudo 包装）
  # PYTHON="$HOME/.venv/bin/python"
  py_exec() {
    if [ -n "$SUDO_CMD" ]; then
      "$SUDO_CMD" "$VENV_BIN" "$@"
    else
      "$VENV_BIN" "$@"
    fi
  }

  # ===== 调用 myshell.py 中的命令 =====
  sh_update_source() {
    py_exec "$ROOT_DIR/myshell.py" sh_update_source "$DISTRO_OSTYPE"
  }

  sh_config_sshd() {
    py_exec "$ROOT_DIR/myshell.py" sh_config_sshd
  }
  # User interaction, cannot use subshells like $(...), use configuration file to pass data
  sh_fix_ip() {
    py_exec "$ROOT_DIR/myshell.py" sh_fix_ip
  }

  sh_clear_cache() {
    py_exec "$ROOT_DIR/myshell.py" sh_clear_cache
  }

  # ===== 调用 mypip.py 中的命令 =====
  sh_install_pip() {
    py_exec "$ROOT_DIR/mypip.py"
  }
fi
