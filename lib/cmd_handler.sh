#!/bin/bash

# Load once only
if [[ -z "${LOADED_CMD_HANDLER:-}" ]]; then
  LOADED_CMD_HANDLER=1

  # ==============================================================================
  # check if package has already been installed
  # 0 = file exist | command exist | service is running
  # 1 = file not exist | command not exist | service does not exist
  # 2 = service exists (but is not running)
  # ==============================================================================
  check_pkg_installed() {
    local chk_cmd="$1"
    [[ -z $chk_cmd ]] && return 0 # NO CHECK NEEDED

    # check if file exist
    if [[ "$chk_cmd" == /* ]]; then
      IFS="|" read -ra cmds <<<"$chk_cmd"
      for cmd in "${cmds[@]}"; do
        [ -e "$chk_cmd" ] && {
          return 0 # file exist
        }
      done
      return 1 # file not exist
    fi

    # check if service is running
    if [[ "$chk_cmd" == *.service ]]; then
      local found=1
      IFS='|' read -ra service_names <<<"$chk_cmd"
      for name in "${service_names[@]}"; do
        [[ "$name" != *.service ]] && name="${name}.service"

        if systemctl is-enabled "$name" &>/dev/null; then
          found=2 # service exist
          if systemctl is-active --quiet "$name"; then
            return 0 # 0=running
          fi
        fi
      done
      return $found # 1=not found | 2=not running
    fi

    # check if program exist and executable
    IFS="|" read -ra cmds <<<"$chk_cmd"
    for cmd in "${cmds[@]}"; do
      command -v "$cmd" &>/dev/null && {
        return 0 # command exist
      }
    done
    return 1 # command not exist
  }

  # ==============================================================================
  # Check if the command exists, if not, install it automatically
  # ==============================================================================
  install_base_pkg() {
    local lnx_cmd="$1"
    local chk_cmd="${2-$1}" # install check command

    [[ -n $chk_cmd ]] && check_pkg_installed "$chk_cmd" && return 0 # program already installed

    # Install command based on different Linux distributions

    if [ "$DISTRO_PM" = "pacman" ]; then # arch Linux
      cmd=("pacman -Sy --noconfirm $lnx_cmd")
    elif [ "$DISTRO_PM" = "apt" ]; then # debian | ubuntu
      cmd=("apt-get install -y $lnx_cmd")
    else # centos | rhel | openSUSE
      cmd=("$DISTRO_PM install -y $lnx_cmd")
    fi

    # message for debug
    if [[ "${DEBUG:-1}" == "0" ]]; then
      string "Automatically installing {} ..." "$lnx_cmd"
    fi

    set +e
    cmd_exec "${cmd[@]}"
    local ret_code=$?
    set -e

    if [[ $ret_code -eq 0 ]]; then
      [[ -z $chk_cmd ]] || check_pkg_installed "$chk_cmd"
      local rc=$?
      if [ $rc -eq 0 ]; then
        success "{} installation successful" "$lnx_cmd"
        return 0 # program installed
      elif [ $rc -eq 2 ]; then
        warning "{} installation successful, but service is not running" "$lnx_cmd"
        return 2 # service is not running
      fi
    fi

    # Check again if the installation was successful
    exiterr "{} installation failed, please install manually. Log: {} [{}]" \
      "$lnx_cmd" "$LOG_FILE" "$(date "+%Y-%m-%d %H:%M:%S")"
  }

  # ==============================================================================
  # cmd_exec - 执行命令并支持日志记录、静默模式、同行输出等功能
  #            日志模式（结果写入日志文件）
  #
  # 参数选项:
  #   cmd...         要执行的命令（除非确有必要，避免使用 && 动态拼接命令！）
  #
  # 返回值:
  #   0 表示成功，非 0 表示失败
  #
  # 示例:
  #   cmd_exec "apt update"  # 单个命令
  #   cmd_exec "apt update" "apt install curl"  # 多个命令
  # ==============================================================================
  cmd_exec() {
    local combined_cmd="" # Combined command line arguments

    # Combine commands using &&
    for cmd in "${@}"; do
      combined_cmd="${combined_cmd:+$combined_cmd && }$cmd"
    done
    combined_cmd=$(echo "$combined_cmd" | xargs) # Remove extra spaces

    # Execute command & monitor progress
    monitor_progress "$combined_cmd" "$LOG_FILE" # Call monitoring function
    return $?                                    # Return the command execution result
  }

  # 监控命令进度并在单行中显示更新
  # 参数：$1 - 进程PID
  monitor_progress() {
    local cmd="$1"
    local log_file="${2:-$LOG_FILE}"

    # 执行命令（非安静模式）
    # bash -c "($cmd) >> \"$log_file\" 2>&1" &
    ( ($cmd) >>"$log_file" 2>&1) &

    # 启动命令并获取 PID
    # eval "$cmd >> \"$log_file\" 2>&1 &"
    local pid=$!

    # 检查 PID 是否为空
    [[ -z "$pid" ]] && {
      echo "Error: Empty PID" >&2
      return 1
    }

    # DEBUG mode skips process detection
    if [[ "${DEBUG:-1}" == "1" ]] && ! kill -0 "$pid" 2>/dev/null; then
      echo "Error: Invalid PID $pid"
      return 1
    fi

    if [[ "${DEBUG:-1}" == "0" ]]; then
      string "Monitoring process {}..." "$pid"
    fi

    local max_width=$(tput cols)
    [[ $max_width -gt 80 ]] && max_width=80

    local spinner='|/-\\'
    local spin_index=0
    local last_size=0
    local latest=""
    while kill -0 "$pid" 2>/dev/null; do
      sleep 0.2

      if [[ -f "$log_file" ]]; then
        local current_size=$(stat -c %s "$log_file" 2>/dev/null || echo 0)

        if [[ $current_size -ne $last_size ]]; then
          # 提取最后有效行，清理控制字符
          latest=$(tail -n 1 "$log_file" | tr -d '[:cntrl:]' | cut -c 1-"$max_width")
          last_size=$current_size
        fi
      fi

      # 始终刷新 spinner + latest
      spin_index=$(((spin_index + 1) % 4))
      printf "\r\033[K[%s] %s" "${spinner:$spin_index:1}" "${latest:-Waiting...}"
    done

    # 显示最终状态
    wait "$pid" 2>/dev/null
    local ret_code=$?
    if [[ $ret_code -eq 0 ]]; then
      printf "\r\033[K[%s] %s" "-" "$(_mf "Completed"): $(date "+%Y-%m-%d %H:%M:%S")"
    fi
    printf "\n"
    return $ret_code # Return the command execution result
  }

  # ==============================================================================
  # Description: Set ownership to $REAL_USER, optionally set permission
  # 功能：将文件或目录归属改为 $REAL_USER，如果提供了权限（如 644），则一并修改
  # ==============================================================================
  user_file_permit() {
    local targets=()
    local autofile=0 # default=auto create file
    local mode=""    # default=do not change mode
    local showinfo=1 # default=do not show info
    if [[ "$REAL_USER" == "root" ]]; then
      return 0
    fi

    # Parse arguments
    for arg in "$@"; do
      case "$arg" in
        --autofile)
          autofile="${arg#*=}"
          ;;
        --mode=*)
          mode="${arg#*=}"
          ;;
        --showinfo)
          showinfo=0
          ;;
        *)
          targets+=("$arg")
          ;;
      esac
    done

    for t in "${targets[@]}"; do
      if [[ ! -e "$t" ]]; then
        if [[ "$autofile" -eq 0 ]]; then
          touch "$t" # Create file if it does not exist
        else
          continue # Target file does not exist, skip it
        fi
      fi
      chown -fR "$REAL_USER:$REAL_USER" "$t"    # change owner
      [[ -n "$mode" ]] && chmod -R "$mode" "$t" # change mode
    done
    if [[ "$showinfo" -eq 0 ]]; then
      printf "%s: %s\n" "$INIT_CHMOD_FILENAME" "${targets[*]}"
      printf "%s: %s\n" "$INIT_CHMOD_USERNAME" "$REAL_USER"
    fi
    return 0
  }
fi
