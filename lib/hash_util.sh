#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_HASH_UTIL:-}" ]]; then
  LOADED_HASH_UTIL=1

  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry
  source "$LIB_DIR/debug_tool.sh"

  # ==============================================================================
  # 语言包hash计算规则（支持20w+函数；每个函数<=4096个消息）
  #  文件名 函数名 - hash自动计算：（64^3 = 262,144）
  #  文件名 函数名 - 冲突线性探测：（：64^1 = 64）
  #  消息调用 - 按出现的顺序排列：（64^2 = 4096）
  # ==============================================================================

  declare -A _LANG_PROPS  # prop definition: key=Hash Code; value = path/program func_name
  declare -A LANG_PROPS   # prop definition: key=Hash Code + "_" + LineNo + "_" + order; value = translated words
  declare -A LANG_PROPS_T # prop definition: key=Hash Code + "_" + position + "_" + order; value = translated words

  hash_init_msg() {
    declare -n _MSG_FUNC_CALLS="$1" # 结果数组 filename function_name line_number matched_type order
    # 当前处理的函数名和哈希码
    current_func=""
    current_hash=""
    current_key=""
    current_count=0 # 跟踪每个哈希码的计数器

    for ((i = 0; i < ${#_MSG_FUNC_CALLS[@]}; i++)); do
      # 获取当前记录
      local record="${_MSG_FUNC_CALLS[i]}"

      # 拆分记录
      # 格式: "bin/i18n.sh load_lang_files info 32 - 查找可用语言..."
      local file func type lineno order msg
      read -r file func type lineno order msg <<<"$record"

      # 当函数名发生变化时，生成新的哈希码
      if [[ "$func" != "$current_func" ]]; then
        _lang_props_set current_hash "${file}@@${func}" # 使用文件名和函数名生成哈希码

        current_func="$func" # 记住当前函数名
        current_hash=$(padded_number_to_base64 "$current_hash"_4)
        current_count=0 # 清空哈希码计数器
      fi
      current_key=${current_hash}$(padded_number_to_base64 "$current_count"_2)
      LANG_PROPS["$current_key"]="$msg" # 存储到 LANG_PROPS
      # 增加计数
      ((current_count++))
    done
  }

  # DJB2 hash function
  hash_djb2() {
    local s="$1" i
    local hash=5381
    # 设置掩码为 64^3-1，确保结果是一个3位64进制数
    local mask=$((64 * 64 * 64 - 1)) # 相当于 64^3-1 = 262,144
    for ((i = 0; i < ${#s}; i++)); do
      hash=$((hash * 33 + $(LC_CTYPE=C printf '%d' "'${s:i:1}")))
      # 使用按位与来限制范围
      hash=$((hash & mask))
    done
    echo $hash
  }

  # change number to base64
  number_to_base64() {
    local num="$1"
    local base64chars="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    local result=""

    # 处理0的特殊情况
    if [ "$num" -eq 0 ]; then
      echo "A" # 0在base64中通常表示为A
      return
    fi

    while [ $num -gt 0 ]; do
      result="${base64chars:((num % 64)):1}$result"
      num=$((num / 64))
    done
    echo "$result"
  }

  # ==============================================================================
  # fixed length 64进制
  # 支持读入多个数值，合并成一个
  # 数值可以指定输出位数，如："123456_3"
  #     结果不满3位，自动左侧填充
  #     结果超过3位，只取右侧3位
  # 如果是这种输入："123456"，则直接输出结果
  # 如果有多个数值，每个数值单独计算，最终结果，依次拼成一个字符串返回
  # 例子：
  # ==============================================================================
  padded_number_to_base64() {
    local result=""

    # 处理每个传入的参数
    for arg in "$@"; do
      local temp=""

      # 检查是否有指定长度 (类似 "123456_3" 的格式)
      if [[ $arg =~ ^([0-9]+)_([0-9]+)$ ]]; then
        local num="${BASH_REMATCH[1]}"
        local length="${BASH_REMATCH[2]}"

        # 计算base64值
        temp=$(number_to_base64 "$num")
        # 保证 $temp 至少有 $length 长度，不足左侧补A
        temp=$(printf "%${length}s" "$temp" | tr ' ' 'A')
        # 截断为右侧 $length 位
        temp="${temp: -$length}"

      else
        # 没有指定长度，直接计算并添加到结果
        temp=$(number_to_base64 "$arg")
      fi
      result="${result}${temp}"
    done

    echo "$result"
  }

  # change base64 to number
  base64_to_number() {
    local s="$1" i result=0
    local chars="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

    # 检查输入是否为空
    if [ -z "$s" ]; then
      echo "0"
      return
    fi

    for ((i = 0; i < ${#s}; i++)); do
      # 找到字符在字符集中的位置
      local position=$(expr index "$chars" "${s:i:1}")
      # 位置减1才是正确的索引值
      result=$((result * 64 + position - 1))
    done
    echo "$result"
  }

  # ==============================================================================
  # Set function: Add a string to the hash table with linear probing
  # 用途: 将给定的字符串存储到全局数组 _LANG_PROPS 中，并返回其哈希索引位置
  #       使用线性探测法解决哈希冲突
  # 参数:
  #   $1 - 返回hash code（引用父函数变量）
  #   $2 - 要存储的字符串（示例格式: "bin/init_base_func.sh@@select_mirror"）
  # 返回值:
  #   返回字符串在数组中的索引位置
  # 算法说明:
  #   1. 使用 djb2 哈希算法计算初始索引
  #   2. 如果发生冲突，使用线性探测法查找下一个可用位置
  #      - 步长从1开始递增，跳过64倍数，超过最大值，则返回到0
  #   3. 如果找到相同字符串，直接返回其现有索引
  #   4. 将新字符串存入数组并返回其索引
  # 全局变量:
  #   _LANG_PROPS - 存储字符串的全局数组
  # ==============================================================================
  _lang_props_set() {
    local -n _idx="$1"                    # 引用父函数的 idx
    local str="$2"                        # sample: "bin/init_base_func.sh@@select_mirror"
    local mask=$((64 * 64 * 64 * 64 - 1)) # 相当于 64^4-1 = 16,777,215
    _idx=$(($(hash_djb2 "$str") * 64))    # 初始索引（64对齐）

    # Linear probing for collision resolution
    while [ -n "${_LANG_PROPS[$_idx]}" ]; do
      [ "${_LANG_PROPS[$_idx]}" = "$str" ] && return # 已存在，直接返回

      _idx=$((($_idx + (($_idx & 63) == 63 ? 2 : 1)) & mask)) # 探测下一个索引（跳过64倍数）
    done
    _LANG_PROPS[$_idx]="$str" # 写入新值
  }

  # ==============================================================================
  # 主程序（用于测试）
  # 扫描目录中的所有shell脚本
  # 解析shell文件中的语言函数
  # ==============================================================================
  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then

    main() {
      # 测试1：base64转换
      local a=1213312
      local b=0
      local b64=$(padded_number_to_base64 ${a}_4 ${b}_2)
      local c=$(base64_to_number "${b64:0:4}") # 前4位
      local d=$(base64_to_number "${b64:4:2}") # 后2位
      test_assertion "[[ $c == $a && $d == $b ]]" "base64 convert: $b64"

      # 测试2：_LANG_PROPS key / value
      a="bin/init_base_func.sh@@select_mirror"
      local idx
      _lang_props_set idx $a
      local b="${_LANG_PROPS[$idx]}"
      test_assertion "[[ $a == $b ]]" "set _LANG_PROPS: $idx"
    }

    main "$@"
  fi

fi
