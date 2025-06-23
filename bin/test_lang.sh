#!/bin/bash

# ==============================================================================
# 函数: show_help_info
# 描述: 根据函数元数据（META_Command）显示帮助信息
# 参数:
#   $1 - 命令名称
# ==============================================================================
show_help_info() {
  local cmd=$1
  [[ -z "$cmd" ]] && exiterr "Usage: show_help_info [command]\n \   
        Available commands: find, ls   "

  # 使用jq解析JSON
  local command_info=$(jq -e ".${cmd}" <<<"$META_Command" 2>/dev/null)
  [[ -z "$command_info" ]] && exiterr "Error: Command '$cmd' not found."

  # 提取命令信息
  name=$(jq -r '.name' <<<"$command_info")

  echo "名称: $name"
  echo "用法: $cmd [选项...]"
  echo ""
  echo "选项:"

  # 提取所有选项并格式化
  jq -r '
  .options[] |
  [
    (if .key != "" then .key + ", " else "    " end) + .long,
    .desc
  ] | @tsv' <<<"$command_info" | while IFS=$'\t' read -r opt desc; do
    # 输出第一行（选项 + 第一行描述）
    printf "  %-24s%s\n" "$opt" "${desc%%$'\n'*}"
    # 如果描述中有多行，继续按行输出
    if [[ "$desc" == *$'\n'* ]]; then
      while IFS= read -r line; do
        printf "%24s%s\n" "" "$line"
      done <<<"${desc#*$'\n'}"
    fi
  done
}

# ==============================================================================
#  删除语言文件
# ==============================================================================
del_lang_files() {
  local lang_code="$1"
  local lang_file=()
  # 获取所有文件路径
  resolve_lang_files lang_file "$lang_code" "0-e"

  # 嵌套删除文件子程序
  do_del_lang_files() {
    local delstr=$(string "{0} 语言文件已删除" "$lang_code")
    rm -f "${lang_file[@]}"
    info -i "$delstr" # ignore translation
  }

  # 如果指定了 noPrompt 为 yes，则直接删除文件
  if [[ "$2" == 1 ]]; then
    do_del_lang_files
    return 0
  fi

  # 文件存在，提示用户是否删除
  local prompt=$(string "确定要删除 {0} 语言文件吗?" "$lang_code")
  confirm_action "$prompt" do_del_lang_files msg="$(string "操作已取消，文件未删除")" # 👈 msg="cancel_msg"
}

# ==============================================================================
#  添加语言文件
# ==============================================================================
add_lang_files() {
  local lang_code="$1"
  local lang_file=()
  # 获取所有文件路径
  resolve_lang_files lang_file "$lang_code" "1+w"

  # 标准模板内容
  local template="$(string "# {0} 语言包，文档结构：\n\
# 1. 自动处理 bin | lib 目录 sh 文件\n\
# 2. 解析函数 string | info | exiterr | error | success | warning\n\
# 3. key=distinct hash code + position + order\n\
# 4. value=localized string" "${lang_code}")"

  # 遍历所有文件路径创建文件
  for file in "${lang_file[@]}"; do
    if [[ ! -f "$file" ]]; then
      echo -e "$template" >"$file"
      info "{0} 语言文件已创建" "$file"
    fi
  done
}
