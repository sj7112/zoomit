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
  PY_REL_DATE="20250517" # 使用稳定的发布版本

  PY_INST_DIR="$HOME/.local/python-$PY_VERSION"
  PY_GZ_FILE="/tmp/cpython-${PY_VERSION}-standalone.tar.gz"
  VENV_DIR="$HOME/.venv"
  VENV_BIN="$HOME/.venv/bin/python"

  # ==============================================================================
  # 安装python虚拟环境
  # ==============================================================================
  # 判断是否已有 Python 3.10+
  check_py_version() {
    local py_path=$1
    if [ -n "$py_path" ] && "$py_path" -c 'import sys; exit(0) if sys.version_info >= (3,10) else exit(1)' 2>/dev/null; then
      # 确保 venv 和 ensurepip 都存在
      if "$py_path" -m venv --help >/dev/null 2>&1 \
        && "$py_path" -m ensurepip --version >/dev/null 2>&1; then
        return 0
      fi
    fi
    return 1
  }

  # 检测系统架构和发行版
  detect_system() {
    local arch=$(uname -m) # 检测架构
    case "$arch" in
      x86_64) arch="x86_64" ;;
      aarch64 | arm64) arch="aarch64" ;;
      armv7l) arch="armv7" ;;
      *) exiterr "不支持的架构: $arch" ;;
    esac

    echo "$arch-linux" # 不考虑linux-musl
  }

  # 获取 Python standalone 下载 URL
  get_python_url() {
    local system_type="$1"

    # 根据系统类型选择合适的构建
    case "$system_type" in
      x86_64-linux)
        echo "$PY_BASE_URL/$PY_REL_DATE/cpython-$PY_VERSION+$PY_REL_DATE-x86_64-unknown-linux-gnu-install_only.tar.gz"
        ;;
      aarch64-linux)
        echo "$PY_BASE_URL/$PY_REL_DATE/cpython-$PY_VERSION+$PY_REL_DATE-aarch64-unknown-linux-gnu-install_only.tar.gz"
        ;;
      *)
        exiterr "不支持的系统类型: $system_type"
        ;;
    esac
  }

  # 增强版智能 wget 函数
  smart_geturl() {
    local output="$1"
    local url="$2"

    # 检查参数
    if [ -z "$output" ] || [ -z "$url" ]; then
      echo "错误: 用法 smart_geturl <输出文件> <URL>"
      return 1
    fi

    # 自动判断是否存在 wget 或 curl
    local downloader=""
    if command -v wget >/dev/null 2>&1; then
      downloader="wget -c -q -O \"$output\" \"$url\""
    elif command -v curl >/dev/null 2>&1; then
      downloader="curl -L -C - -s -o \"$output\" \"$url\""
    else
      echo "错误: 系统未安装 wget 或 curl，无法下载。"
      return 2
    fi

    # 启动后台下载
    echo "开始下载: $downloader"
    echo "开始时间: $(date)"
    eval "$downloader &"
    local pid=$!
    local start_time=$(date +%s)

    # 定义本地退出清理函数
    SMART_WGET_PID=$pid
    on_exit() {
      local oid="$SMART_WGET_PID"
      if kill -0 "$oid" 2>/dev/null; then
        echo ""
        warning "检测到中断，正在终止后台下载进程（PID=$oid...）"
        kill "$oid" 2>/dev/null
        wait "$oid" 2>/dev/null
      fi
    }

    # 开始trap（防止影响全局）
    trap on_exit INT TERM EXIT

    local counter=0
    local prev_size=0
    local display_content=""
    local cached_stats=""
    local elapsed
    local elapsed_formatted

    # 每0.5秒监控循环
    while kill -0 "$pid" 2>/dev/null; do
      counter=$((counter + 1))

      # 旋转指示器（每0.5秒更新）
      case $((counter % 4)) in
        0) spinner="-" ;;
        1) spinner="\\" ;;
        2) spinner="|" ;;
        3) spinner="/" ;;
      esac

      # 计算运行时间
      if [ $((counter % 2)) -eq 0 ] || [ $counter -eq 1 ]; then
        elapsed=$(($(date +%s) - start_time))
        elapsed_formatted=$(printf "%02d:%02d:%02d" $((elapsed / 3600)) $((elapsed % 3600 / 60)) $((elapsed % 60)))
      fi

      # 每3秒进行一次完整计算
      if [ $((counter % 6)) -eq 0 ] || [ $counter -eq 1 ]; then
        # 获取文件大小（字节）
        local current_size
        if [ -f "$output" ]; then
          if stat -c%s "$output" >/dev/null 2>&1; then
            current_size=$(stat -c%s "$output" 2>/dev/null)
          else
            current_size=0
          fi

          # 人类可读大小 (B, K, M, G)
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

          # 计算变化
          local size_change=$((current_size - prev_size))

          # 计算平均速度
          local avg_speed_text="计算中..."
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

          # 缓存统计信息（除了spinner和时间）
          cached_stats=$(string "大小: $human_size ↑$size_change | 平均: $avg_speed_text")
          prev_size=$current_size
        else
          cached_stats="等待文件创建..."
        fi
      fi

      # 每0.5秒更新显示（只更新spinner和当前时间）
      display_content=$(string "$(date '+%H:%M:%S') | 运行时间: $elapsed_formatted | $cached_stats")
      printf "\r\033[K[%s] %s" "${spinner}" "${display_content}"
      sleep 0.5
    done

    # 检查结果
    echo ""
    wait "$pid"

    # 取消trap（避免影响其它代码）
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
      echo "✓ 下载完成! 文件大小: $final_size"
    else
      echo "✗ 下载失败"
      return $exit_code
    fi
  }

  # 下载并安装 Python standalone
  install_py_standalone() {
    local system_type=$(detect_system)
    local python_url=$(get_python_url "$system_type")

    # 下载文件（支持断点续传）
    info "下载 Python {} standalone..." $PY_VERSION

    smart_geturl "$PY_GZ_FILE" "$python_url"

    # 解压到安装目录
    info "安装 Python 到 {}..." "$PY_INST_DIR"
    mkdir -p "$PY_INST_DIR" # 确保安装目录存在
    if ! tar -zxf "$PY_GZ_FILE" -C "$PY_INST_DIR" --strip-components=1; then
      exiterr "解压安装失败"
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
      # 验证是否可用
      if check_py_version "$local_bin"; then
        info "Python $PY_VERSION 安装完成！"
        echo "$local_bin"
      else
        exiterr "Python $PY_VERSION 安装失败: $local_bin 不存在或不可执行"
      fi
    fi
  }

  # 创建虚拟环境并安装常用包
  install_py_venv() {
    # 删除已存在的虚拟环境
    if [[ -d "$VENV_DIR" ]]; then
      if ! confirm_action "虚拟环境 $VENV_DIR 已存在，是否删除重建？" default="N"; then
        confirm_action "是否重建 pip 和所需 python 库？" default="N" msg="跳过虚拟环境创建"
        return $?
      else
        info "删除虚拟环境 $VENV_DIR..."
        $SUDO_CMD rm -rf "$VENV_DIR"
      fi
    fi

    # 找到python系统路径
    local py_bin=$(install_py_bin)

    # 创建python虚拟环境
    info "创建虚拟环境 $VENV_DIR..."
    if "$py_bin" -m venv "$VENV_DIR"; then
      success "虚拟环境创建成功！"
      return 0 # 创建pip
    else
      exiterr "创建虚拟环境失败"
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
    echo -e "✨ 已配置 pip 使用新的镜像"
    echo "   镜像: $mirror_url"
    echo "   信任主机: $host"
    echo ""
  }

  upgrade_pip() {
    run_with_log "$VENV_BIN" -m pip install --upgrade pip
    if [[ $? -eq 0 ]]; then
      echo "[INFO] pip ${CMD_UPGRADE}${CMD_SUCCESS}"
    else
      echo "[ERROR] pip ${CMD_UPGRADE}${CMD_FAILURE}"
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
        echo "[INFO] $pkg ${CMD_INSTALL}${CMD_SUCCESS}"
      else
        echo "[ERROR] $pkg ${CMD_INSTALL}${CMD_FAILURE}"
      fi
    done
  }
  # ==============================================================================
  # 函数: create venv, install pip
  # ==============================================================================
  create_py_venv() {
    # create ~/.venv; install pip; install third party packages
    if install_py_venv; then
      echo "=================================================="
      echo "🌍 测试全球 pip 可用镜像速度..."
      echo "=================================================="

      set +e
      sh_install_pip # test and pick up a faster mirror (User prompt in Python)
      status=$?
      if [[ $status -eq 0 ]]; then       # use sys.exit() to return code
        url=$(cat /tmp/mypip_result.log) # use temp file to return value
        configure_pip "$url"
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
