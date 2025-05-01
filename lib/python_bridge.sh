#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_PYTHON_BRIDGE:-}" ]]; then
  LOADED_PYTHON_BRIDGE=1

  # 声明全局变量
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # bin direcotry
  : "${PYTHON_DIR:=$(dirname "$BIN_DIR")/python}"               # python directory

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

  # ===== 从另一个Python脚本导入的函数示例 =====
  # 例如，从text_processor.py导入函数
  process_text() {
    local input_text="$1"
    local options="$2"

    python3 -c "
import sys
sys.path.append('$PYTHON_DIR')
from text_processor import process_text

result = process_text('$input_text', '$options')
print(result)
"
  }

  # ===== 从data_analyzer.py导入的函数示例 =====
  analyze_data() {
    local data_file="$1"
    local analysis_type="$2"

    # 调用Python并获取结果
    python3 -c "
import sys
sys.path.append('$PYTHON_DIR')
from data_analyzer import analyze_data

results = analyze_data('$data_file', '$analysis_type')
for item in results:
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
