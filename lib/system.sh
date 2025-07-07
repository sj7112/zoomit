#!/bin/bash

# Load once only
if [[ -z "${LOADED_SYSTEM:-}" ]]; then
  LOADED_SYSTEM=1

  TMP_FILE_PREFIX="sj_temp_"

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
  # 自动生成临时文件（用于子函数向父函数传递数据）
  # ==============================================================================
  generate_temp_file() {
    # If nanoseconds not supported, fallback to second-level timestamp
    local timestamp="$(date +%s%N 2>/dev/null || date +%s)"

    # Prefer /dev/shm if it exists and is writable, otherwise fallback to /tmp
    local tmpdir="/tmp"
    [[ -d /dev/shm && -w /dev/shm ]] && tmpdir="/dev/shm"
    # Generate a unique file id with timestamp and random number
    local tmpfile="${tmpdir}/${TMP_FILE_PREFIX}${timestamp}${RANDOM}"
    # shellcheck disable=SC2188
    >"$tmpfile" || {
      echo "Error: Unable to create temp file $tmpfile" >&2
      return 1
    }
    echo "$tmpfile"
  }

  # ==============================================================================
  # Destroy temporary files safely
  # ==============================================================================
  destroy_temp_file() {
    local tmpfile="$1"
    # Only attempt to remove if variable is not empty and file exists
    if [[ -n "$tmpfile" && -e "$tmpfile" ]]; then
      rm -f "$tmpfile"
    fi
  }

  destroy_temp_files() {
    local tmpdir="/tmp"
    [[ -d /dev/shm && -w /dev/shm ]] && tmpdir="/dev/shm"

    # Remove all files starting with sj_temp_ in the tmpdir
    rm -f "${tmpdir}/${TMP_FILE_PREFIX}"* 2>/dev/null || true
  }

fi
