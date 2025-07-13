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
    # Prefer /dev/shm if it exists and is writable, otherwise fallback to /tmp
    local tmpdir="/tmp"
    [[ -d /dev/shm && -w /dev/shm ]] && tmpdir="/dev/shm"
    # Generate a unique file id with timestamp and random number
    local tmpfile="${tmpdir}/${TMP_FILE_PREFIX}$(date +%s)${RANDOM}"
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
  # functions to support temp files
  # ==============================================================================
  init_docker_setup() {
    local filename=$(generate_temp_file)
    export DOCKER_SETUP_FILE="$filename"
  }

  # get timeout value from file
  get_docker_setup() {
    if [[ -n "${DOCKER_SETUP_FILE:-}" && -f "$DOCKER_SETUP_FILE" ]]; then
      # 判断是否有 official 或 available
      url=$(awk -F= '$1=="url"{print $2}' "$DOCKER_SETUP_FILE")
      echo "${url:-""}"
      return
    fi
    echo ""
  }

  # ==============================================================================
  # functions to support read_util.sh
  # ==============================================================================
  # init timeout value and set the evironment variable
  init_time_out() {
    local filename=$(generate_temp_file)
    cat >"$filename" <<EOF
current=$1
backup=999999
EOF
    export TIMEOUT_FILE="$filename"
  }

  # get timeout value from file
  get_time_out() {
    if [[ -z "${TIMEOUT_FILE:-}" || ! -f "$TIMEOUT_FILE" ]]; then
      echo "999999" # not set, return default value
    else
      local val=$(grep '^current=' "$TIMEOUT_FILE" | cut -d'=' -f2)
      echo "${val:-999999}" # return value from the file
    fi
  }

  # switch timeout value
  toggle_time_out() {
    local timeout="999999" # default value
    if [[ -n "${TIMEOUT_FILE}" && -f "$TIMEOUT_FILE" ]]; then
      local curr="999999"
      local back="60"
      while IFS='=' read -r key val; do
        case "$key" in
          current) curr="$val" ;;
          backup) back="$val" ;;
        esac
      done <"$TIMEOUT_FILE"
      echo -e "current=$back\nbackup=$curr" >"$TIMEOUT_FILE"
      timeout="$back" # switch to backup value
    fi
    echo "$timeout" # return the new value

    # print ^X and clean after 0.3s
    printf "^X=%s" "$timeout" >&2
    (
      sleep 0.3
      len=$((3 + ${#timeout}))
      printf -- '\b%.0s %.0s\b%.0s' $(seq 1 $len) $(seq 1 $len) $(seq 1 $len) >&2
    ) &
  }

  # Function to clear the input buffer (incl. Enter, spaces, etc.)
  clear_input() {
    local dummy
    while read -rs -t 0 dummy; do :; done
  }

  return_feedback() {
    local response="$1" # current input
    local no_value="$2"
    if [[ -z "$response" ]]; then
      echo "$no_value" # set default value
    else
      echo "${response// /}" # Remove whitespace characters
    fi
    printf "\n" >&2
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
      printf "\r%s %s\033[K" "$prompt" "$new_response" >&2 # multibyte character: Redraw the entire line
    else
      printf "\b \b" >&2 # ASCII: Use backspace-space-backspace sequence
    fi

    echo "$new_response"
  }

  # Check if timeout is reached
  check_timeout() {
    local response="$1"
    local to_value="$2"
    local start_time="$3"
    local timeout="$4"

    if [[ -z $response && $(($(date +%s) - start_time)) -ge timeout ]]; then
      echo "$to_value"
      printf "%s\n" "$to_value" >&2
      return 0
    fi

    echo "$response"
    return 1
  }

  # ==============================================================================
  # functions to support auto run parameter
  # ==============================================================================
  init_param_fixip() {
    if [[ -z "${PARAM_FILE:-}" || ! -f "$PARAM_FILE" ]]; then
      local filename=$(generate_temp_file)
      cat >"$filename" <<EOF
ip_last_octet=$1
EOF
      export PARAM_FILE="$filename"
    else
      local filename=$PARAM_FILE
      cat >>"$filename" <<EOF
ip_last_octet=$1
EOF
    fi
  }

  get_param_fixip() {
    if [[ -z "${PARAM_FILE:-}" || ! -f "$PARAM_FILE" ]]; then
      echo "0" # not set, return default value
    else
      local val=$(grep '^ip_last_octet=' "$PARAM_FILE" | cut -d'=' -f2)
      echo "${val:-1}" # return value from the file
    fi
  }

fi
