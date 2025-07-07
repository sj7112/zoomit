#!/bin/bash

# Load once only
if [[ -z "${LOADED_PYTHON_BRIDGE:-}" ]]; then
  LOADED_PYTHON_BRIDGE=1

  # Declare global
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # bin direcotry
  : "${ROOT_DIR:=$(dirname "$BIN_DIR")}"                        # project root directory

  # python3 virtual environment: $HOME/.venv/bin/python
  py_exec() {
    "$REAL_HOME/.venv/bin/python" "$@"
  }

  # ===== 调用 myshell.py 中的命令 =====
  sh_update_source() {
    echo
    py_exec "$ROOT_DIR/myshell.py" sh_update_source "$DISTRO_OSTYPE"
  }

  sh_configure_sshd() {
    set +e
    py_exec "$ROOT_DIR/myshell.py" sh_configure_sshd
    local ret_code=$?
    set -e
    return $ret_code
  }
  # User interaction, cannot use subshells like $(...), use configuration file to pass data
  sh_fix_ip() {
    set +e
    py_exec "$ROOT_DIR/myshell.py" sh_fix_ip
    local ret_code=$?
    set -e
    return $ret_code
  }

  sh_clear_cache() {
    if [[ ! -f "$VENV_BIN" ]]; then
      exiterr "Python executable file {} does not exist" "$VENV_BIN"
    fi
    py_exec "$ROOT_DIR/myshell.py" sh_clear_cache
  }

  # ===== 调用 mypip.py 中的命令 =====
  sh_install_pip() {
    py_exec "$ROOT_DIR/mypip.py"
  }
fi
