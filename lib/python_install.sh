#!/bin/bash

# Load once only
if [[ -z "${LOADED_PYTHON_INSTALL:-}" ]]; then
  LOADED_PYTHON_INSTALL=1

  # Declare global
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # bin direcotry
  source "$LIB_DIR/msg_handler.sh"
  source "$LIB_DIR/bash_utils.sh"
  source "$LIB_DIR/python_bridge.sh"

  LOG_FILE="/var/log/sj_install.log"
  ERR_FILE="/var/log/sj_pkg_err.log"

  PY_BASE_URL="https://github.com/astral-sh/python-build-standalone/releases/download"
  PY_VERSION="3.10.17"
  PY_REL_DATE="20250517" # Use a stable release version

  PY_INST_DIR="$HOME/.local/python-$PY_VERSION"
  PY_GZ_FILE="/tmp/cpython-${PY_VERSION}-standalone.tar.gz"
  VENV_DIR="$HOME/.venv"
  VENV_BIN="$HOME/.venv/bin/python"

  mirror_list=() # 👈 Define as a global array
  fail_list=()

  # ==============================================================================
  # Install Python virtual environment
  # ==============================================================================
  # Check if Python 3.10+ is already available
  check_py_version() {
    local py_path=$1
    if [ -n "$py_path" ] && "$py_path" -c 'import sys; exit(0) if sys.version_info >= (3,10) else exit(1)' 2>/dev/null; then
      # Ensure both venv and ensurepip are available
      if "$py_path" -m venv --help >/dev/null 2>&1 \
        && "$py_path" -m ensurepip --version >/dev/null 2>&1; then
        return 0
      fi
    fi
    return 1
  }

  # Detect system architecture and distribution
  detect_system() {
    local arch=$(uname -m) # Detect architecture
    case "$arch" in
      x86_64) arch="x86_64" ;;
      aarch64 | arm64) arch="aarch64" ;;
      armv7l) arch="armv7" ;;
      *) exiterr "Unsupported architecture: {}" "$arch" ;;
    esac

    echo "$arch-linux" # Does not consider linux-musl
  }

  # Get Python standalone download URL
  get_python_url() {
    local system_type="$1"

    # Select the appropriate build based on the system type
    case "$system_type" in
      x86_64-linux)
        echo "$PY_BASE_URL/$PY_REL_DATE/cpython-$PY_VERSION+$PY_REL_DATE-x86_64-unknown-linux-gnu-install_only.tar.gz"
        ;;
      aarch64-linux)
        echo "$PY_BASE_URL/$PY_REL_DATE/cpython-$PY_VERSION+$PY_REL_DATE-aarch64-unknown-linux-gnu-install_only.tar.gz"
        ;;
      *) exiterr "Unsupported system type: {}" "$system_type" ;;
    esac
  }

  # Enhanced smart wget function
  smart_geturl() {
    local output="$1"
    local url="$2"

    # Check parameters
    if [ -z "$output" ] || [ -z "$url" ]; then
      error "Usage: smart_geturl <output_file> <URL>"
      return 1
    fi

    # Automatically determine if wget or curl is available
    local downloader=""
    if command -v wget >/dev/null 2>&1; then
      downloader="wget -c -q -O \"$output\" \"$url\""
    elif command -v curl >/dev/null 2>&1; then
      downloader="curl -L -C - -s -o \"$output\" \"$url\""
    else
      error "Neither wget nor curl is installed on the system, unable to download."
      return 2
    fi

    # Start background download
    echo "$(_mf "Starting download"): $downloader"
    echo "$(_mf "Start time"): $(date)"
    eval "$downloader &"
    local pid=$!
    local start_time=$(date +%s)

    # Define local cleanup function on exit
    SMART_WGET_PID=$pid
    on_exit() {
      local oid="$SMART_WGET_PID"
      if kill -0 "$oid" 2>/dev/null; then
        echo ""
        warning "Interrupt detected, terminating background download process (PID={}...)" "$oid"
        kill "$oid" 2>/dev/null
        wait "$oid" 2>/dev/null
      fi
    }

    # Begin trap (to prevent affecting global scope)
    trap on_exit INT TERM EXIT

    local counter=0
    local prev_size=0
    local display_content=""
    local cached_stats=""
    local elapsed
    local elapsed_formatted

    # Monitor loop every 0.5 seconds
    while kill -0 "$pid" 2>/dev/null; do
      counter=$((counter + 1))

      # Rotating spinner (updates every 0.5 seconds)
      case $((counter % 4)) in
        0) spinner="-" ;;
        1) spinner="\\" ;;
        2) spinner="|" ;;
        3) spinner="/" ;;
      esac

      # Calculate runtime
      if [ $((counter % 2)) -eq 0 ] || [ $counter -eq 1 ]; then
        elapsed=$(($(date +%s) - start_time))
        elapsed_formatted=$(printf "%02d:%02d:%02d" $((elapsed / 3600)) $((elapsed % 3600 / 60)) $((elapsed % 60)))
      fi

      # Perform a full calculation every 3 seconds
      if [ $((counter % 6)) -eq 0 ] || [ $counter -eq 1 ]; then
        # Get file size (in bytes)
        local current_size
        if [ -f "$output" ]; then
          if stat -c%s "$output" >/dev/null 2>&1; then
            current_size=$(stat -c%s "$output" 2>/dev/null)
          else
            current_size=0
          fi

          # Human-readable size (B, K, M, G)
          local human_size
          if [ "$current_size" -gt 1073741824 ]; then
            human_size="$(echo "$current_size" | awk '{printf "%.1fG", $1/1073741824}')"
          elif [ "$current_size" -gt 1048576 ]; then
            human_size="$(echo "$current_size" | awk '{printf "%.0fM", $1/1048576}')"
          elif [ "$current_size" -gt 1024 ]; then
            human_size="$(echo "$current_size" | awk '{printf "%.0fK", $1/1024}')"
          else
            human_size="${current_size}B"
          fi

          # Calculate size change
          local size_change=$((current_size - prev_size))

          # Calculate average speed
          local avg_speed_text="Calculating..."
          if [ "$elapsed" -gt 0 ] && [ "$current_size" -gt 0 ]; then
            local avg_speed=$((current_size / elapsed))
            if [ "$avg_speed" -gt 1048576 ]; then
              avg_speed_text="$(echo "$avg_speed" | awk '{printf "%.1fMB/s", $1/1048576}')"
            elif [ "$avg_speed" -gt 1024 ]; then
              avg_speed_text="$(echo "$avg_speed" | awk '{printf "%.1fKB/s", $1/1024}')"
            else
              avg_speed_text="${avg_speed}B/s"
            fi
          fi

          # Cache statistics (excluding spinner and time)
          cached_stats="$(_mf "Size"): $human_size ↑$size_change | $(_mf "Average"): $avg_speed_text"
          prev_size=$current_size
        else
          cached_stats=$(_mf "Waiting for file creation...")
        fi
      fi

      # Update display every 0.5 seconds (only update spinner and current time)
      display_content="$(date '+%H:%M:%S') | $(_mf "Elapsed Time"): $elapsed_formatted | $cached_stats"
      printf "\r\033[K[%s] %s" "${spinner}" "${display_content}"
      sleep 0.5
    done

    # Check the result
    echo ""
    wait "$pid"

    # Remove trap (to avoid affecting other code)
    trap - INT TERM EXIT

    local exit_code=$?
    if [ $exit_code -eq 0 ] && [ -f "$output" ]; then
      local final_size
      if [ -f "$output" ]; then
        local final_bytes
        if stat -c%s "$output" >/dev/null 2>&1; then
          final_bytes=$(stat -c%s "$output")
        fi

        if [ "$final_bytes" -gt 1048576 ]; then
          final_size="$(echo "$final_bytes" | awk '{printf "%.1fMB", $1/1048576}')"
        else
          final_size="$(du -h "$output" 2>/dev/null | cut -f1)"
        fi
      fi
      echo "✓ $(_mf "Download complete! File size"): $final_size"
    else
      echo "✗ $(_mf "Download failed")"
      return $exit_code
    fi
  }

  # Download and install Python standalone
  install_py_standalone() {
    local system_type=$(detect_system)
    local python_url=$(get_python_url "$system_type")

    # Download file (supports resuming)
    info "Downloading Python {} standalone..." $PY_VERSION

    smart_geturl "$PY_GZ_FILE" "$python_url"

    # Extract to the installation directory
    info "Installing Python to {}..." "$PY_INST_DIR"
    mkdir -p "$PY_INST_DIR" # Ensure the installation directory exists
    if ! tar -zxf "$PY_GZ_FILE" -C "$PY_INST_DIR" --strip-components=1; then
      exiterr "Extraction and installation failed"
    fi
  }

  install_py_bin() {
    local default_bin="$(command -v python3 2>/dev/null || true)"
    local local_bin="${PY_INST_DIR}/bin/python3"

    # Check if Python needs to be reinstalled
    if check_py_version "$default_bin"; then
      echo "$default_bin"
    elif check_py_version "$local_bin"; then
      echo "$local_bin"
    else
      install_py_standalone
      # Verify if it is usable
      if check_py_version "$local_bin"; then
        info "Python {} installation completed!" "$PY_VERSION"
        echo "$local_bin"
      else
        exiterr "Python {} installation failed: {} does not exist or is not executable" "$PY_VERSION" "$local_bin"
      fi
    fi
  }

  # Create a virtual environment and install common packages
  install_py_venv() {
    # Remove existing virtual environment
    if [[ -d "$VENV_DIR" ]]; then
      local prompt=$(_mf "Virtual environment {} already exists. Delete and reinstall it?" "${VENV_DIR}")
      if ! confirm_action "$prompt" default="N"; then
        echo ""
        local pip_url=$("$VENV_BIN" -m pip config get global.index-url 2>/dev/null)
        local mirror_str=""
        if [[ -n $pip_url ]]; then
          mirror_str="$(_mf "Current pip mirror:") ${pip_url}"$'\n'
        fi
        prompt=$(_mf "{}Reinstall pip and the required Python libraries?" "$mirror_str")
        confirm_action "$prompt" default="N" msg="$(_mf "Skipping virtual environment creation")"
        return $?
      else
        info "Deleting virtual environment {}..." "$VENV_DIR"
        $SUDO_CMD rm -rf "$VENV_DIR"
      fi
    fi

    # Find the Python system path
    local py_bin=$(install_py_bin)

    # Create Python virtual environment
    info "Creating virtual environment {}..." "$VENV_DIR"
    if "$py_bin" -m venv "$VENV_DIR"; then
      success "Virtual environment created successfully"
      return 0 # Create pip
    else
      exiterr "Failed to create virtual environment"
    fi
  }

  # ==============================================================================
  # 封装命令执行函数并返回状态code（自动生成正常日志，错误信息同时进错误日志）
  # ==============================================================================
  run_with_log() {
    local cmd=("$@")
    "${cmd[@]}" >>"$LOG_FILE" 2> >(tee -a "$ERR_FILE" >>"$LOG_FILE")
    return ${PIPESTATUS[0]}
  }

  configure_pip() {
    local mirror_url="$1"

    # 提取主机名作为 trusted-host
    host=$(echo "$mirror_url" | awk -F/ '{print $3}')

    # 设置 index-url
    run_with_log "$VENV_BIN" -m pip config set global.index-url "$mirror_url"
    if [[ $? -ne 0 ]]; then
      echo "Config index-url failure"
      return 1
    fi

    # 设置 trusted-host
    if [[ "$mirror_url" =~ ^http:// ]]; then
      run_with_log "$VENV_BIN" -m pip config set global.trusted-host "$host"
      if [[ $? -ne 0 ]]; then
        echo "Config trusted-host failure"
        return 1
      fi
    fi
    echo ""
    echo -e "✨ $(_mf "Pip has been configured to use the new mirror")"
    echo "   $(_mf "Mirror"): $mirror_url"
    echo "   $(_mf "Trusted Host"): $host"
    echo ""
  }

  upgrade_pip() {
    run_with_log "$VENV_BIN" -m pip install --upgrade pip
    if [[ $? -eq 0 ]]; then
      string "[INFO] pip upgrade success"
    else
      string "[ERROR] pip upgrade failure"
    fi
  }

  install_packages() {
    packages=(
      typer       # CLI framework
      ruamel.yaml # YAML processing
      requests    # HTTP library
      iso3166     # Lookup country names
      diskcache   # Cache for translation messages
      # pydantic  # Data validation
    )

    for pkg in "${packages[@]}"; do
      run_with_log "$VENV_BIN" -m pip install "$pkg"
      if [[ $? -eq 0 ]]; then
        string "[INFO] {} install success" "$pkg"
      else
        string "[ERROR] {} install failure" "$pkg"
      fi
    done
  }

  # get result for all mirrors after test speed
  show_pip_mirrors() {
    log_file="/tmp/mypip_mirror_list.log"

    # Read and categorize records
    while IFS="|" read -r status name url time; do
      if [[ "$status" == "success" ]]; then
        mirror_list+=("$name|$url|$time")
      else
        fail_list+=("$name|$url|$status")
      fi
    done <"$log_file"

    # Print successful records
    if [[ ${#mirror_list[@]} -gt 0 ]]; then
      # Calculate column widths
      max_name=4
      max_url=0
      for item in "${mirror_list[@]}"; do
        IFS="|" read -r name url time <<<"$item"
        ((${#name} > max_name)) && max_name=${#name}
        ((${#url} > max_url)) && max_url=${#url}
      done
      ((max_name += 4))
      ((max_url += 4))

      # Print header
      printf "%-9s%-*s%-*s%-8s\n" "$(_mf "Index")" "$max_name" "$(_mf "Mirror Name")" "$max_url" "$(_mf "URL Address")" "$(_mf "Time")"
      printf "%0.s-" $(seq 1 $((max_name + max_url + 16))) && echo

      # Print data
      i=1
      for item in "${mirror_list[@]}"; do
        IFS="|" read -r name url time <<<"$item"
        printf "%-4d %-*s %-*s %7.2fs\n" "$i" $max_name "$name" $max_url "$url" "$time"
        ((i++))
      done

      # Fastest mirror (first entry)
      IFS="|" read -r fastest_name fastest_url fastest_time <<<"${mirror_list[0]}"
      echo
      echo "🚀 $(_mf "Fastest Mirror"): $fastest_name"
      echo "   $(_mf "URL Address"): $fastest_url"
      printf "   $(_mf "Response Time"): %.2fs\n" "$fastest_time"
    fi

    # Print failed records
    if [[ ${#fail_list[@]} -gt 0 ]]; then
      echo
      echo "❌ $(_mf "Failed Mirrors") (${#fail_list[@]}):"

      max_name=0
      max_url=0
      for item in "${fail_list[@]}"; do
        IFS="|" read -r name url status <<<"$item"
        ((${#name} > max_name)) && max_name=${#name}
        ((${#url} > max_url)) && max_url=${#url}
      done
      ((max_name += 4))
      ((max_url += 4))

      printf "%-*s %-*s %8s\n" $max_name "$(_mf "Mirror Name")" $max_url "$(_mf "URL Address")" "$(_mf "Status")"
      printf "%0.s-" $(seq 1 $((max_name + max_url + 8))) && echo

      for item in "${fail_list[@]}"; do
        IFS="|" read -r name url status <<<"$item"
        # Translate status to English
        case "$status" in
          timeout) status_msg="Timeout" ;;
          failed) status_msg="Failed" ;;
          error) status_msg="Error" ;;
          *) status_msg="$status" ;;
        esac
        printf "%-*s %-*s %8s\n" $max_name "$name" $max_url "$url" "$status_msg"
      done
    fi
  }

  # Select a mirror from the list of available mirrors
  choose_pip_mirror() {
    local len=${#mirror_list[@]}
    local choice
    local choice_num
    local selected_mirror
    local url

    if [[ $len -eq 0 ]]; then
      string "\n⚠️  No available mirrors found. Please check your network connection."
      return 3
    fi

    while true; do
      local prompt="\n$(_mf "Please select a mirror to use. Enter 0 to skip") (0-$len): "
      read -rp "$prompt" choice
      choice="${choice// /}" # Remove whitespace characters
      if [[ "$choice" == "0" ]]; then
        string "Configuration canceled. Keeping current settings"
        return 1
      fi

      # Check if input is an integer
      if [[ "$choice" =~ ^[0-9]+$ ]]; then
        choice_num=$((choice))
        if ((choice_num >= 1 && choice_num <= len)); then
          selected_mirror="${mirror_list[choice_num - 1]}"
          # Mirror sample: AARNET (Australia)|https://pypi.aarnet.edu.au/simple/|0.4954190254211426
          url="${selected_mirror%%|*}" # Extract the first segment (name)
          url="${selected_mirror#*|}"  # Remove the first segment and delimiter
          url="${url%%|*}"             # Extract the second segment (URL)
          echo "$url"
          return 0
        fi
      fi

      string "[ERROR] Invalid input! Please enter a number between 0 and {}." "$len"
    done
  }

  # ==============================================================================
  # Main function: create venv, install pip
  # ==============================================================================
  create_py_venv() {
    # create ~/.venv; install pip; install third party packages
    if install_py_venv; then
      echo ""
      echo "=================================================="
      echo "🌍 $(_mf "Testing global pip mirror speeds...")"
      echo "=================================================="

      set +e
      sh_install_pip # python adds-on: test and pick up a faster mirror
      local status=$?
      if [[ $status -eq 0 ]]; then # use sys.exit() to return code
        show_pip_mirrors
        url=$(choose_pip_mirror)
        status=$?
        # url=$(cat /tmp/mypip_result.log) # use temp file to return value
        [[ $status -eq 0 ]] && configure_pip "$url"
      fi
      set -e

      if [[ $status -eq 0 || $status -eq 1 ]]; then
        upgrade_pip
        install_packages
      fi
      echo ""
    fi
  }

  # ==============================================================================
  # 主程序（用于测试）
  # ==============================================================================
  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then

    set -euo pipefail # Exit on error, undefined vars, and failed pipes

    # 主函数
    main() {
      info "Python $PY_VERSION Standalone 自动安装脚本"
      create_py_venv
    }

    # 执行主函数
    main "$@"
  fi

fi
