#!/bin/bash

# Load once only
if [[ -z "${LOADED_NETWORK:-}" ]]; then
  LOADED_NETWORK=1

  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # lib direcotry

  LOG_FILE="/var/log/sj_install.log"

  # 初始化函数：读取python传入的.env对象并初始化
  init_env_nw() {
    while IFS='=' read -r key value; do
      [[ -z "$key" || "$key" == '#' ]] && continue
      # 根据section存入不同数组
      ENV_NETWORK["$key"]="$value"
      keys_network+=("$key")
    done <"$ENV_NW_PATH"
  }

  # ==============================================================================
  # 计数器函数
  # ==============================================================================
  count_down() {
    # 设置环境变量
    local count=6
    local IFACE="${ENV_NETWORK["MAIN_IFACE"]}"
    local IP_ADDR="${ENV_NETWORK["STATIC_IP"]}"

    # ANSI color
    local BG_BLUE="\033[44m"
    local NC="\033[0m" # reset color

    info "Change network in {} seconds: {} (interface {}). Please be ready to reconnect. Press Ctrl+C to cancel" "$count" "$IP_ADDR" "$IFACE"
    for i in $(seq "$count" -1 1); do
      echo -ne "${BG_BLUE}  $i 秒 ${NC}\r"
      sleep 0.5
    done
    echo -e "${BG_BLUE}  0 秒 ${NC}"
  }

  # ==============================================================================
  # 配置静态IP（NetworkManager）
  # ==============================================================================
  config_nmcli() {
    # 检查 nmcli 是否存在
    if ! command -v nmcli &>/dev/null; then
      exiterr "nmcli is not installed or unavailable. Please install it and try again"
    fi

    # 设置环境变量
    IFACE="${ENV_NETWORK["MAIN_IFACE"]}"  # 网络接口名
    CON_NAME="static-$IFACE"              # 连接名称，NetworkManager 中标识配置的名字
    IP_ADDR="${ENV_NETWORK["STATIC_IP"]}" # IP 地址（不含掩码）
    PREFIX="${ENV_NETWORK["PREFIX"]:-24}" # 子网掩码长度，默认24
    GATEWAY="${ENV_NETWORK["GATEWAY"]}"   # 网关
    DNS="${ENV_NETWORK["DNS_SERVERS"]}"   # DNS 服务器，多个用空格隔开

    # 1. 查看连接是否存在，不存在则创建
    if ! $SUDO_CMD nmcli connection show "$CON_NAME" &>/dev/null; then
      $SUDO_CMD nmcli connection add type ethernet ifname "$IFACE" con-name "$CON_NAME"
    fi

    # 2. 修改连接为静态 IP
    $SUDO_CMD nmcli connection modify "$CON_NAME" \
      ipv4.addresses "$IP_ADDR/$PREFIX" \
      ipv4.gateway "$GATEWAY" \
      ipv4.dns "$DNS" \
      ipv4.method manual \
      connection.autoconnect yes

    # 3. 激活连接
    count_down # Countdown reminder
    $SUDO_CMD nmcli connection up "$CON_NAME" || exiterr "Failed to restart NetworkManager. Please check and try again"

  }

  # Comment out network configuration
  comment_ifupdown() {
    IFACE="${ENV_NETWORK["MAIN_IFACE"]}" # Network interface name

    local NET_FILE="/etc/network/interfaces"

    if [[ -f "$NET_FILE" ]]; then
      # backup original network file
      $SUDO_CMD cp "$NET_FILE" "${NET_FILE}.$(date +%Y%m%d_%H%M%S)"

      # comment lines: ^allow-hotplug | ^iface
      $SUDO_CMD sed -i "/^[[:space:]]*allow-hotplug.*$IFACE/s/^/# /" "$NET_FILE"
      $SUDO_CMD sed -i "/^[[:space:]]*iface.*$IFACE/s/^/# /" "$NET_FILE"

      info "comment {} for {}" "$NET_FILE" "$IFACE"
    fi
  }

  # ==============================================================================
  # 配置静态IP（例如：/etc/systemd/network/10-ens192.network）
  # ==============================================================================
  setup_systemd_networkd() {
    IFACE="${ENV_NETWORK["MAIN_IFACE"]}"  # Network interface name
    IP_ADDR="${ENV_NETWORK["STATIC_IP"]}" # IP 地址（不含掩码）
    PREFIX="${ENV_NETWORK["PREFIX"]:-24}" # 子网掩码长度，默认24
    GATEWAY="${ENV_NETWORK["GATEWAY"]}"   # Gateway
    DNS="${ENV_NETWORK["DNS_SERVERS"]}"   # DNS server，多个用空格分隔

    local NETDIR="/etc/systemd/network"

    # 1. 检查配置文件
    local NET_FILE="$NETDIR/10-$IFACE.network"
    if [ -f "$NET_FILE" ]; then
      $SUDO_CMD cp "$NET_FILE" "$NET_FILE.$(date +%Y%m%d_%H%M%S)"
    else
      $SUDO_CMD mkdir -p "$NETDIR" # Create directory
    fi

    # 2. 生成配置文件
    $SUDO_CMD cat >"$NET_FILE" <<EOF
[Match]
Name=$IFACE

[Network]
DHCP=no
Address=$IP_ADDR/$PREFIX
Gateway=$GATEWAY
DNS=$DNS
EOF

    string "change config file {}" "$NET_FILE"
  }

  # ==============================================================================
  # 配置切换脚本代码（networking -> systemd-networkd）
  # ==============================================================================
  setup_switch_network() {
    # 创建切换脚本并在后台执行
    $SUDO_CMD cat >/tmp/switch_network.sh <<EOF
#!/bin/bash
exec >> "$LOG_FILE" 2>&1  # add to log data

set -x  # show all commands
echo "=== Switch Network start - \$(date) ==="
$SUDO_CMD systemctl stop networking
$SUDO_CMD systemctl disable networking
$SUDO_CMD pkill dhclient
$SUDO_CMD pkill dhcpcd
$SUDO_CMD systemctl enable --now systemd-networkd
$SUDO_CMD systemctl enable --now systemd-resolved
echo "=== Switch Network end - \$(date) ==="

# clean up
$SUDO_CMD rm -f /tmp/switch_network.sh
EOF

    $SUDO_CMD chmod +x /tmp/switch_network.sh
  }

  # ==============================================================================
  # 配置静态IP（ifupdown -> systemd_networkd）
  # ==============================================================================
  ifupdown_to_systemd_networkd() {
    install_base_pkg "systemd" # install systemd-networkd

    comment_ifupdown       # comment ifupdown config file
    setup_systemd_networkd # create systemd-netwrokd config file
    setup_switch_network   # 创建切换脚本

    count_down # Countdown reminder
    $SUDO_CMD setsid /tmp/switch_network.sh </dev/null &

  }

  # ==============================================================================
  # 配置静态IP（systemd_networkd）
  # ==============================================================================
  config_default() {
    # 检查必要工具和目录
    if ! command -v networkctl &>/dev/null; then
      exiterr "systemd-networkd is not installed or unavailable"
    fi

    setup_systemd_networkd # 生成配置文件

    # 重载配置并重启 networkd
    count_down # Countdown reminder
    if ! $SUDO_CMD systemctl restart systemd-networkd; then
      exiterr "Failed to restart systemd-networkd. Please check and try again"
    fi

  }

  # ==============================================================================
  # main function: network configuration
  # ==============================================================================
  network_config() {
    if [[ ${ENV_NETWORK["CURR_NM"]} == "NetworkManager" ]]; then
      string "NetworkManager is running (systemctl status NetworkManager)"
      config_nmcli
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "networking" ]]; then
      string "ifupdown is running (systemctl status networking)"
      ifupdown_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "wicked" ]]; then
      string "wicked is running (systemctl status wicked)"
      # wicked_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "network" ]]; then
      string "network-scripts is running (systemctl status network)"
      # network_to_systemd_networkd
    elif [[ ${ENV_NETWORK["CURR_NM"]} == "systemd-networkd" ]]; then
      # /etc/systemd/network/10-$IFACE.network
      string "systemd-networkd is running (systemctl status systemd-networkd)"
      config_default
    else
      exiterr "Unknown network manager. Unable to configure static IP"
    fi
  }

fi
