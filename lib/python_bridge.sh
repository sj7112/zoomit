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
      env LANG="$LANG" LANGUAGE="$LANGUAGE" $SUDO_CMD "$HOME/.venv/bin/python" "$@"
    else
      env LANG="$LANG" LANGUAGE="$LANGUAGE" "$HOME/.venv/bin/python" "$@"
    fi
  }

  # ===== 调用 myshell.py 中的命令 =====
  sh_check_ip() {
    py_exec "$PYTHON_DIR/myshell.py" sh_check_ip "$SUDO_CMD" </dev/tty
  }

  sh_install_pip() {
    py_exec "$PYTHON_DIR/myshell.py" sh_install_pip
  }

  sh_update_source() {
    py_exec "$PYTHON_DIR/myshell.py" sh_update_source "$DISTRO_OSTYPE"
  }

  # ===== 从ast_parser.py导入的函数 =====
  parse_shell_files() {
    local sh_file="$1"

    # 直接输出处理结果
    python3 -c "
import sys
sys.path.append('$PYTHON_DIR')
from lang_util import parse_shell_files

for item in parse_shell_files('$sh_file'):
    print(item)
"
  }

  # ===== 支持复杂参数的函数示例 =====
  complex_function() {
    local input_file="$1"
    local output_file="$2"
    local json_config="$3" # 复杂的JSON配置

    # 使用临时文件传递复杂参数
    local temp_config_file
    temp_config_file=$(mktemp)
    echo "$json_config" >"$temp_config_file"

    # 调用Python函数
    python3 -c "
import sys, json
sys.path.append('$PYTHON_DIR')
from complex_processor import process_with_config

with open('$temp_config_file', 'r') as f:
    config = json.load(f)

process_with_config('$input_file', '$output_file', config)
"

    # 清理临时文件
    rm -f "$temp_config_file"
  }

fi
