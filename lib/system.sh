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
  # Generate a unique temporary file path (pass data from a sub-shell to a parent)
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

  # ==============================================================================
  # functions to support read -rsn1
  # ==============================================================================
  # init timeout value and set the evironment variable
  init_time_out() {
    local filename=$(generate_temp_file)
    cat >"$filename" <<EOF
current=$1
backup=999999
EOF
    export CONF_TIME_OUT="$filename"
  }

  # get timeout value from file
  get_time_out() {
    if [[ -z "${CONF_TIME_OUT:-}" || ! -f "$CONF_TIME_OUT" ]]; then
      echo "999999" # not set, return default value
    else
      local val=$(grep '^current=' "$CONF_TIME_OUT" | cut -d'=' -f2)
      echo "${val:-999999}" # return value from the file
    fi
  }

  # switch timeout value
  toggle_time_out() {
    if [[ -z "${CONF_TIME_OUT:-}" || ! -f "$CONF_TIME_OUT" ]]; then
      echo "999999" # not set, return default value
    else
      local curr=$(grep '^current=' "$CONF_FILE" | cut -d'=' -f2)
      local back=$(grep '^backup=' "$CONF_FILE" | cut -d'=' -f2)
      echo -e "current=$back\nbackup=$curr" >"$CONF_FILE"
      # Provide default values to prevent incomplete file content
      curr="${curr:-999999}"
      back="${back:-60}"
      echo -e "current=$back\nbackup=$curr" >"$CONF_FILE"
      echo "$back" # return the new value
    fi
  }

  # Function to clear the input buffer (incl. Enter, spaces, etc.)
  clear_input() {
    local dummy
    while read -r -t 0.01 dummy; do :; done 2>/dev/null
  }

  show_ctrl_t_feedback() {
    printf "^T"
    # 后台进程，0.3秒后清除
    (
      sleep 0.3
      printf "\b\b  \b\b"
    ) &
  }

  safe_backspace() {
    local prompt="$1"   # prompt string shown at start of line
    local response="$2" # current accumulated input
    local new_response=""

    if [[ -z "$response" ]]; then
      echo "$response" # return unchanged
      return
    fi

    local last_char="${response: -1}"
    local byte_length=$(LC_ALL=C printf '%s' "$last_char" | wc -c)

    new_response="${response%?}"
    if [[ $byte_length -gt 1 ]]; then
      echo -ne "\r$prompt $new_response\033[K" >&2 # multibyte character: Redraw the entire line
    else
      echo -ne "\b \b" >&2 # ASCII: Use backspace-space-backspace sequence
    fi

    echo "$new_response"
  }

  # Check if timeout is reached
  check_timeout() {
    local start_time=$1 timeout=$2
    (($(date +%s) - start_time >= timeout))
  }

fi
