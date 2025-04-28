#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_INIT_BASE_FUNC:-}" ]]; then
  LOADED_INIT_BASE_FUNC=1

  # ==============================================================================
  # check_root_file - 检测文件（需root权限）是否存在
  # ==============================================================================
  check_root_file() {
    $SUDO_CMD test -f "$1"
  }

  # ==============================================================================
  # check_root_path - 检测路径（需root权限）是否存在
  # ==============================================================================
  check_root_path() {
    $SUDO_CMD test -f "$1"
  }

  # ==============================================================================
  # select_mirror - 处理镜像选择
  # 适用：debian | ubuntu
  # 参数：
  #   $1 - 包含多个镜像URL的字符串（空格/换行分隔）
  # 返回值：
  #   通过全局变量 SELECTED_MIRROR 返回用户选中的镜像URL
  # ==============================================================================
  select_mirror() {
    # 检查文件是否存在
    [ -f "$1" ] || exiterr "错误：镜像列表文件不存在"

    # 读取并过滤有效镜像
    echo ""
    local mirrors=()
    local count=0
    while IFS= read -r line; do
      line=$(echo "$line" | xargs) # 去除前导空白
      [[ -z "$line" ]] && continue
      if [[ "$line" =~ ^(http|https|ftp):// ]]; then
        ((count = count + 1))
        mirrors[$count]="$line"
        printf "%2d) %s\n" "$count" "$line"
      fi
    done <"$1"
    # 检查是否找到有效镜像
    [ "$count" -gt 0 ] || exiterr "错误：未找到有效镜像URL"
    echo ""

    success "可用的镜像站："

    # 用户选择循环
    while true; do
      echo -ne $(string "请选择镜像编号 [{0}]: " "${RED}1-$count${NC}")
      read choice

      # 检查输入是否有效
      if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le 10 ]; then
        SELECTED_MIRROR="${mirrors[$choice]}"
        break
      else
        echo -e $(string "输入{0}错误!{1}" $RED_BG $NC)
      fi
    done
  }

  # ==============================================================================
  # ping_fastest_mirrors - 测试并返回网络延迟最低的10个HTTP镜像站点
  # 适用：ubuntu
  # 参数：
  #   $1 - 包含多个镜像URL的字符串（空格/换行分隔）
  # 返回值：
  #   通过标准输出返回延迟最低的10个HTTP镜像URL，每行一个
  # ==============================================================================
  ping_fastest_mirrors() {
    local URL DOMAIN AVG_LATENCY
    for URL in $1; do
      if [[ $URL =~ ^http:// ]]; then
        DOMAIN=$(echo "$URL" | awk -F/ '{print $3}')
        AVG_LATENCY=$(ping -c 4 -i 0.2 -q "$DOMAIN" 2>/dev/null | grep rtt | awk '{print $4}' | cut -d/ -f2)
        if [ -n "$AVG_LATENCY" ]; then
          printf "%.2f ms %s\n" "$AVG_LATENCY" "$URL"
        fi
      fi
    done | sort -n | head -10 | awk '{print $3}'
  }

fi
