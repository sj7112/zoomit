#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_JSON_HANDLER:-}" ]]; then
  LOADED_JSON_HANDLER=1

  CONF_DIR="$(dirname "$BIN_DIR")/config" # config direcotry
  LIB_DIR="$(dirname "$BIN_DIR")/lib"     # lib direcotry
  source "$LIB_DIR/debug_tool.sh"

  # 从 config 加载 json文件
  json_load_data() {
    local name="$1"
    local json_file="$CONF_DIR/${name}.json"

    # 检查文件是否存在
    [[ ! -f "$json_file" ]] && {
      echo "配置文件不存在: $json_file" >&2
      return 1
    }

    # 去除 // 和 /* */ 注释，并返回纯净 JSON 数据
    sed -e 's@//.*@@' -e '/\/\*/,/\*\//d' "$json_file" | jq -c .
  }

  # 加载json环境变量
  declare META_Command=$(json_load_data "cmd_meta") # 命令解析json

  # 获取JSON对象的所有key并用指定分隔符连接
  # 用法: json_get_keys "jsonstr" "delimiter"
  json_get_keys() {
    local json_str="$1"
    local delimiter="${2:-,}" # 默认分隔符为逗号
    jq -r "keys | join(\"$delimiter\")" <<<"$json_str"
  }

  # used by json_getopt
  fetch_options() {
    if [[ -n "$1" ]] && jq -e . <<<"$$1" >/dev/null 2>&1; then
      echo -e "$1"
    else
      exiterr -s "JSON format error"
    fi
  }

  # ==============================================================================
  # 简单命令行选项：封装 jq 查询，避免重复代码
  # 注1：内部调试只能用echo "..." >&2 ！！！否则父函数接收echo输出时，会出错
  # 注2：只返回状态码（0/1），不输出值。所以外层调用只能用于判断，不能赋值！！！
  # 需要测试，得在外层加测试语句：json_getopt "$options" "f" && echo "选项 f 存在" || echo "选项 f 不存在"
  # ==============================================================================
  json_getopt() {
    local value=$(jq -r --arg k "$2" '.[$k]' <<<"$1") # options在父函数中定义
    [[ "$value" != "0" && "$value" != "" ]]           # 1 = true(0)；0|"" = false(1)
  }

  # 检查是否json格式
  json_check() {
    local json="$1"
    if ! jq empty <<<"$json" 2>/dev/null; then
      return 1
    fi
  }

  # ==============================================================================
  # 解析函数中的命令行选项（Short options & Long options）
  #
  # 注1：调试只能用echo "..." >&2 ！！！否则父函数接收echo输出时，会出错
  # 注2：short_opt遇到echo坑点：-n会被改为""
  # ==============================================================================
  parse_options() {
    local parsed_options="{}" # 选项JSON对象
    if [ -n "$META_Command" ]; then
      # 从META_Command中提取选项定义
      local cmd_name=${FUNCNAME[1]}
      local options_def=$(json get META_Command "${cmd_name}.options")
      if [[ -z "$options_def" || "$options_def" == "null" ]]; then
        echo "检查 META_Command 未包含 $cmd_name 格式" >&2
        exit 1
      fi

      local json_key
      local -A short_opts_map   # 短选项名 -> 布尔值（用于检查是否为有效选项）
      local -A long_opts_map    # 长选项名 -> 布尔值（用于检查是否为有效选项）
      local -A long_to_json_key # 长选项名 -> JSON键名

      # 填充映射表并初始化 parsed_options
      while read -r key long; do
        local def_val=0 # 默认存0
        if [[ "$key" =~ ^-[a-zA-Z0-9]$ ]]; then
          # 短选项
          json_key="${key#-}"           # 去除前缀"-"
          short_opts_map["$json_key"]=1 # 用于检查是否为有效选项
          if [[ -n "$long" ]]; then
            long_opts_map["${long#--}"]=1              # 用于检查是否为有效选项
            long_to_json_key["${long#--}"]="$json_key" # 有长选项
            def_val=""                                 # 存空串
          fi
        else
          # 长选项
          json_key="${key#--}"         # 去除前缀"--"
          long_opts_map["$json_key"]=1 # 用于检查是否为有效选项
          def_val=""                   # 存空串
        fi
        json set parsed_options "$json_key" "$def_val" # 将该选项添加到parsed_options，初始值为0

      done < <(jq -r '.[] | [.key, (.long // "")] | join(" ")' <<<"$options_def")

      # 当前函数所有参数一览表
      # list_vars "$(extract_local_variables)" "$(declare -p)" "$@"
      # echo "$parsed_options" >&2
      # print_array short_opts_map
      # print_array long_opts_map
      # print_array long_to_json_key

      # 解析参数
      local new_args=()
      local i=1
      while [[ $i -le $# ]]; do
        local arg="${!i}"
        # 处理带值的长选项 --option=value

        case "$arg" in
          --*) # 处理长选项 (--file, --single, --quiet)
            IFS='=' read -r key value <<<"$arg"
            key="${key#--}"
            json_key="${long_to_json_key["$key"]:-$key}"

            if [[ -v "long_opts_map[$json_key]" ]]; then
              value="${value:-1}"
              json set parsed_options "$json_key" "$value"
            else
              echo "警告: 未知选项 $arg" >&2
            fi
            ;;

          -*) # 处理短选项（单个 -f 或组合 -fs）
            local short_opt="${arg#-}"
            # 处理每个字符
            for ((j = 0; j < ${#short_opt}; j++)); do
              json_key="${short_opt:$j:1}"

              if [[ -v "short_opts_map[$json_key]" ]]; then
                json set parsed_options "$json_key" 1
              else
                echo "警告: 未知选项 -$json_key" >&2
              fi
            done
            ;;

          *) # 非选项参数视为命令
            new_args+=("$arg")
            ;;
        esac
        ((i = i + 1))
      done
    fi
    echo "set -- $(printf "%q " "$parsed_options" "${new_args[@]}")"
  }

  # ==============================================================================
  # JSON 操作函数，支持嵌套路径和特殊字符
  # 用法示例：
  #   json new MY_JSON '{"user":{"name":"John"}}'
  #   json set MY_JSON "user.address.city" "New York"
  #   json get MY_JSON
  #   json get MY_JSON "user.address.city"
  # ==============================================================================
  json() {
    local cmd=$1
    shift

    case "$cmd" in
      new)
        local varname=$1
        local initial=${2:-'{}'}

        # 验证初始JSON是否有效
        if ! echo "$initial" | jq -e '.' &>/dev/null; then
          echo "错误: 无效的初始JSON" >&2
          return 1
        fi

        # 设置变量
        eval "$varname='$initial'"
        ;;

      set)
        local varname=$1
        local path=$2
        local value=$3
        local json_data=${!varname}
        local tmp_value_file=$(mktemp)
        local result

        # 将值写入临时文件以保留特殊字符
        echo -n "$value" >"$tmp_value_file"

        # 检查值是否为有效JSON
        if [[ -n "$value" && $(echo "$value" | jq -e 'type == "object" or type == "array"' &>/dev/null 2>&1) ]]; then
          # 值是有效的JSON对象或数组
          is_json=true
        else
          is_json=false
        fi

        if [[ "$path" == *"."* ]]; then
          # 处理嵌套路径
          local filter
          local parts=(${path//./ })
          local jq_path=""

          # 构建JQ路径表达式
          for part in "${parts[@]}"; do
            jq_path+="[\"$part\"]"
          done

          # 根据值类型选择合适的JQ命令
          if $is_json; then
            result=$(jq --argjson v "$value" "$jq_path = \$v" <<<"$json_data")
          else
            result=$(jq --rawfile v "$tmp_value_file" "$jq_path = \$v" <<<"$json_data")
          fi
        else
          # 处理顶层键
          if $is_json; then
            result=$(jq --arg k "$path" --argjson v "$value" '.[$k] = $v' <<<"$json_data")
          else
            result=$(jq --arg k "$path" --rawfile v "$tmp_value_file" '.[$k] = $v' <<<"$json_data")
          fi
        fi

        # 更新变量
        if [[ $? -eq 0 ]]; then
          eval "$varname=\$result"
        else
          echo "错误: 设置路径 '$path' 失败" >&2
          rm -f "$tmp_value_file"
          return 1
        fi

        # 清理临时文件
        rm -f "$tmp_value_file"
        ;;

      get)
        local varname=$1
        local path=$2
        local json_data=${!varname}

        # 如果 path 为空，直接返回整个 json_data
        if [[ -z "$path" ]]; then
          echo "$json_data"
          return
        fi

        # 将路径分割成 parentPath 和 currentPath
        local parentPath="${path%%.*}" # 获取 . 前面的部分
        local currentPath="${path#*.}" # 获取 . 后面的部分

        # 如果 currentPath 为空，表示只需要获取 parentPath 对应的数据
        if [[ "$path" == *.* ]]; then
          # 使用 jq 进行索引，获取嵌套路径数据并去掉引号
          jq -r --arg cmd "$parentPath" --arg path "$currentPath" '.[$cmd][$path]' <<<"$json_data"
        else
          # 直接返回 parentPath 对应的数据并去掉引号
          jq -r --arg cmd "$parentPath" '.[$cmd]' <<<"$json_data"
        fi
        ;;

      delete)
        local varname=$1
        local path=${2:-""}

        if [[ -z "$path" ]]; then
          # 删除整个变量
          unset "$varname"
        else
          local json_data=${!varname}
          local result

          if [[ "$path" == *"."* ]]; then
            # 删除嵌套路径
            local parts=(${path//./ })
            local jq_path=""

            # 构建JQ路径表达式
            for part in "${parts[@]}"; do
              jq_path+="[\"$part\"]"
            done

            result=$(jq "del($jq_path)" <<<"$json_data")
          else
            # 删除顶层键
            result=$(jq --arg k "$path" 'del(.[$k])' <<<"$json_data")
          fi

          # 更新变量
          eval "$varname=\$result"
        fi
        ;;

      check)
        local varname=$1
        local path=$2
        local json_data=${!varname}
        local exists

        # 检查路径是否存在
        if [[ "$path" == *"."* ]]; then
          # 处理嵌套路径
          local parts=(${path//./ })
          local jq_path=""

          for part in "${parts[@]}"; do
            jq_path+="[\"$part\"]"
          done

          exists=$(jq -e "getpath($jq_path) != null" <<<"$json_data")
        else
          # 处理顶层键
          exists=$(jq -e --arg k "$path" 'has($k)' <<<"$json_data")
        fi

        if [[ $exists == "true" ]]; then
          return 0
        else
          echo "错误: 路径 '$path' 不存在" >&2
          return 1
        fi
        ;;
    esac
  }

fi
