#!/bin/bash

# Load once only
if [[ -z "${LOADED_BASH_UTILS:-}" ]]; then
  LOADED_BASH_UTILS=1

  do_confirm_action() {
    local result_f="${1:-}" # Temp file to store result
    local prompt="$2"
    local no_value="$3"
    local to_value="$4"
    local err_handle="$5"
    local error_msg="$6"

    local timeout="${CONF_TIME_OUT:-999999}" # 999999=永不超时
    local rc

    trap 'exit 130' INT

    while true; do
      read -t "$timeout" -rp "$prompt " response
      rc=$?
      if [[ $rc -eq 0 ]]; then
        if [[ -z "$response" ]]; then
          response=$no_value # set default value
        else
          response="${response// /}" # Remove whitespace characters
        fi
      elif [[ $rc -eq 130 ]]; then
        return 130 # 被中断
      elif [[ $rc -gt 128 ]]; then
        response="$to_value" # 超时或其他信号 (包括142)
      else
        exit $rc
      fi

      # 选项为 [YyNn]
      if [[ "$option" == "bool" ]]; then
        if [[ ! "$response" =~ ^[YyNn]$ ]]; then
          if [[ -n $err_handle ]]; then
            "$err_handle" "$response" "$error_msg"
            local err_code=$?
            [[ $err_code == 2 ]] && echo && continue # 0 = continue
            [[ $err_code == 3 ]] && exit 3           # 3 = exit
          else
            string "Please enter 'y' for yes, 'n' for no, or press Enter for default"
            continue
          fi
        fi
        [[ "$response" =~ ^[Yy]$ ]] && exit 0 || exit 1

      # 选项为 数值
      elif [[ "$option" == "number" ]]; then
        if [[ -n $err_handle ]]; then
          "$err_handle" "$response" "$error_msg"
          local err_code=$?
          [[ $err_code == 2 ]] && echo && continue # 0 = continue
          [[ $err_code == 3 ]] && exit 3           # 3 = exit
        elif [[ ! "$response" =~ ^[0-9]+$ ]]; then
          string "[{}] Invalid input! Please enter a number" "$MSG_ERROR"
          continue
        fi
        echo "$response" >"$result_f"
        exit 0

      # 选项为 字符或字符串
      elif [[ "$option" == "string" ]]; then
        if [[ -n $err_handle ]]; then
          "$err_handle" "$response" "$error_msg"
          local err_code=$?
          [[ $err_code == 2 ]] && echo && continue # 0 = continue
          [[ $err_code == 3 ]] && exit 3           # 3 = exit
        fi
        echo "$response" >"$result_f"
        exit 0
      fi
    done

    trap - INT
  }

  # ==============================================================================
  # Confirmation function with callback
  # Parameters:
  #   $1: prompt message
  #   $2+: callback function name and its arguments
  # Optional parameters:
  #   option="bool | number | string": define action type (default: bool)
  #   msg="text": one message for above 3 messages (default: "operation is cancelled")
  #   no_msg="text": custom message for NO (default: "operation is cancelled")
  #   error_msg="text": custom message for wrong value (default: "operation is cancelled")
  #   exit_msg="text": custom message for user exit ctrl+C (default: "operation is cancelled")
  #   err_handle="0/1 | Function": when error occurs, 1 = exit; 0 = continue
  #   no_value="0=Y|1=N|Others...": default value for Press Enter (default: Y | 0 | None)
  #   to_value="0=Y|1=N|Others...": auto value for Timeout
  # Returns:
  #   0: yes = user entered Y or y; or success = right value
  #   1: no = user entered N or n
  #   2: User interrupt to exit the program
  #   3: System exception to exit the program
  # ==============================================================================
  confirm_action() {
    local prompt="$1"
    shift

    local option="bool" # default: bool
    local msg           # default: empty
    local no_msg        # default: empty
    local error_msg     # default: empty
    local exit_msg      # default: empty
    local err_handle    # default: empty
    local no_value      # default: Y | 0 | None
    local to_value      # default: no_value

    # Parse optional parameters
    local args=()
    while [[ $# -gt 0 ]]; do
      case "$1" in
        option=*) option="${1#option=}" ;;
        msg=*) msg="${1#msg=}" ;;
        no_msg=*) no_msg="${1#no_msg=}" ;;
        error_msg=*) error_msg="${1#error_msg=}" ;;
        exit_msg=*) exit_msg="${1#exit_msg=}" ;;
        err_handle=*) err_handle="${1#err_handle=}" ;;
        no_value=*) no_value="${1#no_value=}" ;;
        to_value=*) to_value="${1#to_value=}" ;;
        *) args+=("$1") ;;
      esac
      shift
    done

    # set default messages if not provided
    msg="${msg:-}"
    [[ -n "$msg" ]] && no_msg="$msg" error_msg="$msg" exit_msg="$msg"
    local def_msg=$(_mf "operation is cancelled")
    no_msg="${no_msg:-${def_msg}}"
    error_msg="${error_msg:-${def_msg}}"
    exit_msg="${exit_msg:-${def_msg}}"

    # Determine default behavior based on def_val parameter
    if [[ "$option" == "bool" ]]; then
      no_value="${no_value:-"Y"}" # Default:
      prompt="$prompt $([[ "$no_value" == "Y" ]] && echo "[Y/n]" || echo "[y/N]")"
    elif [[ "$option" == "number" ]]; then
      no_value="${no_value:-0}" # Default: 0
    elif [[ "$option" == "string" ]]; then
      no_value="${no_value:-""}" # Default: 空字符串
    fi

    to_value="${to_value:-${no_value}}" # timeout: default value = no_value
    err_handle="${err_handle:-}"        # default: no error handler

    # Use result_f to store the user's input (only for number | string callback)
    local result_f=$([[ $option != "bool" ]] && generate_temp_file || echo "") # Generate a temp file
    set +e
    (do_confirm_action "$result_f" "$prompt" "$no_value" "$to_value" "$err_handle" "$error_msg")
    local rc=$?
    set -e

    # echo "ON_EXIT_CODE = $ON_EXIT_CODE"
    if [[ "$rc" -eq 0 ]]; then
      if [[ ${#args[@]} -gt 0 ]]; then
        if [[ $option != "bool" ]]; then
          "${args[@]}" "$(<"$result_f")"
        else
          "${args[@]}"
        fi
        return $?
      fi
    elif [[ "$rc" -eq 1 ]]; then
      warning "$no_msg"
    elif [[ "$rc" -eq 2 ]]; then
      warning "$error_msg"
    elif [[ "$rc" -eq 130 ]]; then
      echo
      warning "$exit_msg"
    else
      echo
      exiterr "$exit_msg"
    fi
    return $rc
  }

fi
