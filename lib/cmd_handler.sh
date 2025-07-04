#!/bin/bash

# Load once only
if [[ -z "${LOADED_CMD_HANDLER:-}" ]]; then
  LOADED_CMD_HANDLER=1

  # ==============================================================================
  # install_base_pkg - 检查命令是否存在，不存在自动安装
  # ==============================================================================
  install_base_pkg() {
    local lnx_cmd="$1"
    # 检查命令是否存在
    if ! command -v "$lnx_cmd" &>/dev/null; then
      string "Automatically installing {} ..." "$lnx_cmd"

      # 根据不同 Linux 发行版安装命令
      if [ "$DISTRO_PM" = "pacman" ]; then # arch Linux
        cmd=("pacman -Sy --noconfirm $lnx_cmd")
      elif [ "$DISTRO_PM" = "apt" ]; then # debian | ubuntu
        cmd=("apt-get install -y $lnx_cmd")
      else # centos | rhel | openSUSE
        cmd=("$DISTRO_PM install -y $lnx_cmd")
      fi
      local result=$(cmd_exec "${cmd[@]}")

      # 再次检查是否安装成功
      local date=$(date "+%Y-%m-%d %H:%M:%S")
      if [ -z "$result" ] || ! command -v "$lnx_cmd" &>/dev/null; then
        exiterr "{} installation failed, please install manually. Log: {} [{}]" "$lnx_cmd" "$LOG_FILE" "$date"
      else
        success "{} installation successful" "$lnx_cmd"
      fi
    fi
  }

  # ==============================================================================
  # 函数: clean_pkg_mgr 清理缓存
  # ==============================================================================
  # clean_pkg_mgr() {
  #   info "清理 {0} 缓存..." "$DISTRO_PM"
  #   local result=0 # 默认成功
  #   case "$DISTRO_PM" in
  #     apt) cmd="apt-get clean" ;;
  #     yum | dnf) cmd="$DISTRO_PM clean all" ;;
  #     zypper) cmd="zypper clean -a" ;;
  #     pacman) cmd="pacman -Sc --noconfirm" ;;
  #   esac
  #   cmd_exec "$cmd" || exiterr "清理缓存失败"
  # }

  # ==============================================================================
  # 函数: update_pkg_mgr 更新镜像源列表
  # ==============================================================================
  # update_pkg_mgr() {
  #   info "更新镜像源列表..."
  #   case "$DISTRO_PM" in
  #     apt) cmd="apt-get update -q" ;;
  #     yum | dnf) cmd="$DISTRO_PM update -q -y" ;;
  #     zypper) cmd="zypper refresh" ;;
  #     pacman) cmd="pacman -Syy" ;;
  #   esac
  #   cmd_exec "$cmd" || exiterr "更新失败，镜像可能不可用"
  # }

  # ==============================================================================
  # 函数: upgrade_pkg_mgr 升级已安装的软件包
  # ==============================================================================
  # upgrade_pkg_mgr() {
  #   info "升级已安装的软件包..."
  #   case "$DISTRO_PM" in
  #     apt) cmd="apt-get upgrade -y" ;;
  #     yum | dnf) cmd="$DISTRO_PM upgrade -y" ;;
  #     zypper) cmd="zypper update -y" ;;
  #     pacman) cmd="pacman -Syu --noconfirm" ;;
  #   esac
  #   cmd_exec "$cmd" || exiterr "升级软件包失败"
  # }

  # ==============================================================================
  # 函数: remove_pkg_mgr 删除不再需要的依赖包
  # ==============================================================================
  # remove_pkg_mgr() {
  #   info "删除不再需要的依赖包..."
  #   case "$DISTRO_PM" in
  #     apt) cmd="apt-get autoremove -y" ;;
  #     yum | dnf) cmd="$DISTRO_PM autoremove -y" ;;
  #     zypper) cmd="zypper remove -u" ;;
  #     pacman) cmd="pacman -Rns $(pacman -Qdtq) --noconfirm" ;;
  #   esac
  #   cmd_exec "$cmd" || exiterr "删除依赖包失败"
  # }

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
    local combined_cmd="" # 合并后的命令行参数
    local result=0        # 返回成功=0 | 失败=1

    # 合并命令，用 && 连接
    for cmd in "${@}"; do
      combined_cmd="${combined_cmd:+$combined_cmd && }$cmd"
    done
    combined_cmd=$(echo "$combined_cmd" | xargs) # 去除多余空格

    # 执行命令 & 监控进度
    monitor_progress "$combined_cmd" "$LOG_FILE" # 调用监控函数
    return $?                                    # 返回命令执行结果
  }

  # 监控命令进度并在单行中显示更新
  # 参数：$1 - 进程PID
  monitor_progress() {
    local cmd="$1"
    local log_file="${2:-$LOG_FILE}"

    # 执行命令（非安静模式）
    if [[ "$cmd" == *"&&"* ]]; then
      $SUDO_CMD bash -c "($cmd) >> \"$log_file\" 2>&1" & # 命令组加上括号
    else
      $SUDO_CMD bash -c "($cmd) >>\"$log_file\" 2>&1" & # 单个命令同样加上($cmd)防信号丢失
    fi

    # 启动命令并获取 PID
    # eval "$cmd >> \"$log_file\" 2>&1 &"
    local pid=$!

    # 检查 PID 是否为空
    [[ -z "$pid" ]] && {
      echo "Error: Empty PID" >&2
      return 1
    }

    # 检查 PID 是否有效（DEBUG跳过检测，避免kill之前进程已结束）
    if [[ "${DEBUG:-0}" != "1" ]] && ! kill -0 "$pid" 2>/dev/null; then
      echo "Error: Invalid PID $pid"
      return 1
    fi

    if [[ "${DEBUG:-0}" == "1" ]]; then
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
    printf "\r\033[K[%s] %s" "-" "$(_mf "Completed"): $(date "+%Y-%m-%d %H:%M:%S")"
    printf "\n"
    wait "$pid" 2>/dev/null
    return $?
  }

  # ==============================================================================
  # Description: Set ownership to $REAL_USER, optionally set permission
  # 功能：将文件或目录归属改为 $REAL_USER，如果提供了权限（如 644），则一并修改
  # ==============================================================================
  user_permit() {
    local mode targets=()

    # Parse arguments
    for arg in "$@"; do
      if [[ "$arg" == --mode=* ]]; then
        mode="${arg#*=}"
      else
        targets+=("$arg")
      fi
    done

    for t in "${targets[@]}"; do
      # Skip if path does not exist
      if [[ -e "$t" ]]; then
        chown -fR "$REAL_USER:$REAL_USER" "$t"
        [[ -n "$mode" ]] && chmod -R "$mode" "$t"
      fi
    done
  }
fi
