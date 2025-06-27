#!/bin/bash

# Load once only
if [[ -z "${LOADED_SYSTEM:-}" ]]; then
  LOADED_SYSTEM=1

  declare -A TMP_MAP # 定义全局关联数组

  # ==============================================================================
  # get_locale_code - 获取locale代码
  # ==============================================================================
  get_locale_code() {
    local locale=""
    # 从多个可能的环境变量中获取
    for var in LANG LC_ALL LC_MESSAGES; do
      if [[ -n "${!var}" ]]; then
        locale="${!var%%.*}" # 去除 .UTF-8 等后缀
        if [[ -n "$locale" ]]; then
          echo "$locale"
          return 0
        fi
      fi
    done
    # 默认返回 en（英语）
    echo "en"
    return 1
  }

  # ==============================================================================
  # generate_tmp_id - 自动生成临时全局变量（用于子函数向父函数传递数据）
  # ==============================================================================
  generate_tmp_id() {
    # try nanosecond-level timestamp
    local uid="$(date +%s%N 2>/dev/null)"
    # if %N is not allowed, change to second-level timestamp
    if ! [[ "$uid" =~ ^[0-9]+$ ]]; then
      uid="$(date +%s)"
    fi

    # legal unique global paramter
    uid="id_${uid}${RANDOM}" # id_ + timestamp + random (0 ~ 32767)

    # Return the variable name
    echo "$uid"
  }

  # ==============================================================================
  # fetch_tmp_id - 获取临时全局变量
  # ==============================================================================
  fetch_tmp_id() {
    local uid="$1"

    # 检查是否存在该键
    if [[ -n "${TMP_MAP[$uid]+x}" ]]; then
      echo "${TMP_MAP[$uid]}"
    else
      echo "No value found for UID: $uid"
    fi
  }

  # ==============================================================================
  # destroy_tmp_id - 销毁临时全局变量
  # ==============================================================================
  destroy_tmp_id() {
    unset TMP_MAP["$1"]
  }

fi
