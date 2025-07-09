#!/bin/bash

# Load once only
if [[ -z "${LOADED_BASH_UTILS:-}" ]]; then
  LOADED_BASH_UTILS=1

  action_handler() {
    local result_f="${1:-}" # Temp file to store result
    local response="$2"
    local option="$3" # "bool" | "number" | "string"
    local err_handle="$4"
    local error_msg="$5"

    # Boolean option [YyNn]
    if [[ "$option" == "bool" ]]; then
      if [[ ! "$response" =~ ^[YyNn]$ ]]; then
        if [[ -n $err_handle ]]; then
          "$err_handle" "$response" "$error_msg"
          return $? # 2 = continue, 3 = exit
        else
          string "Please enter 'y' for yes, 'n' for no, or press Enter for default"
          return 2 # 2 = continue
        fi
      fi
      [[ "$response" =~ ^[Yy]$ ]] && return 0 || return 1

    # Number option
    elif [[ "$option" == "number" ]]; then
      if [[ ! "$response" =~ ^[0-9]+$ ]]; then
        string "[{}] Invalid input! Please enter a number" "$MSG_ERROR"
        return 2 # 2 = continue
      elif [[ -n $err_handle ]]; then
        "$err_handle" "$response" "$error_msg"
        local err_code=$?
        [[ $err_code != 0 ]] && return $err_code # 2 = continue, 3 = exit
      fi
      echo "$response" >"$result_f"
      return 0

    # String option
    elif [[ "$option" == "string" ]]; then
      if [[ -n $err_handle ]]; then
        "$err_handle" "$response" "$error_msg"
        local err_code=$?
        [[ $err_code != 0 ]] && return $err_code # 2 = continue, 3 = exit
      fi
      echo "$response" >"$result_f"
      return 0
    fi

  }

  do_confirm_action() {
    local result_f="${1:-}" # Temp file to store result
    local prompt="$2"
    local option="$3" # "bool" | "number" | "string"
    local no_value="$4"
    local to_value="$5"
    local err_handle="$6"
    local error_msg="$7"

    local timeout=$(get_time_out) # 999999=永不超时
    local rc

    orig_stty=$(stty -g)
    trap 'stty "$orig_stty"; exit 130' INT # if tty does not show characters, use `stty echo` or `stty sane`

    while true; do
      response=""
      start_time=$(date +%s)
      clear_input
      echo -n "$prompt " >&2

      while true; do
        # Read one character with 0.5s timeout for responsiveness
        read -rsn1 -t 0.5 key
        rc=$?
        if [[ $rc -eq 0 ]]; then
          if [[ -z "$key" ]]; then # Enter (End of line)
            echo >&2
            break
          elif [[ $key == $'\x14' ]]; then # Ctrl+T (timeout toggle)
            timeout="$(toggle_time_out)"
            start_time=$(date +%s)
            show_ctrl_t_feedback
          elif [[ $key == $'\x7f' || $key == $'\b' ]]; then # Backspace (ASCII 127 | ASCII 8)
            response=$(safe_backspace "$prompt" "$response")
          else # Normal character input
            response+="$key"
            echo -n "$key" >&2
          fi
        elif [[ $rc -gt 128 || $rc -eq 142 ]]; then # Check timeout if response is empty
          if [[ -z $response ]] && check_timeout "$start_time" "$timeout"; then
            echo >&2
            response=$to_value # Timeout reached, set timeout value
            break
          fi
        elif [[ $rc -eq 1 ]]; then
          break # Ctrl+D (EOF — End Of File)
        elif [[ $rc -eq 130 ]]; then
          exit 130 # Ctrl+C to exit (may not run, because "trap" has higher priority)
        else
          exit $rc # Exit with the error code
        fi
      done

      # read -t "$timeout" -rp "$prompt " response
      # rc=$?
      # if [[ $rc -eq 0 ]]; then
      if [[ -z "$response" ]]; then
        response=$no_value # set default value
      else
        response="${response// /}" # Remove whitespace characters
      fi
      # elif [[ $rc -eq 130 ]]; then
      #   return 130 # 被中断
      # elif [[ $rc -gt 128 ]]; then
      #   echo >&2
      #   response=$to_value # 超时或其他信号 (包括142)
      # else
      #   echo >&2
      #   exit $rc
      # fi

      action_handler "$result_f" "$response" "$option" "$err_handle" "$error_msg"
      rc=$?
      if [[ $rc -eq 2 ]]; then
        echo >&2
        continue # Continue to prompt again
      else
        exit $rc # Exit the function
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
  #   msg="text": one message for above 3 messages (default: "Operation cancelled")
  #   no_msg="text": custom message for NO (default: "Operation cancelled")
  #   error_msg="text": custom message for wrong value (default: "Operation cancelled")
  #   exit_msg="text": custom message for user exit ctrl+C (default: "Operation cancelled")
  #   err_handle="0/1 | Function": when error occurs, 1 = exit; 0 = continue
  #   no_value="0=Y|1=N|Others...": default value for Press Enter (default: Y | 0 | None)
  #   to_value="0=Y|1=N|Others...": auto value for Timeout
  # Returns:
  #   0: yes = user entered Y or y; or success = right value
  #   1: no = user entered N or n
  #   2: Error handler: to be continued
  #   3: Error handler: to exit the program
  #   130: Ctrl+C SIGNAL to exit the program
  #   142: Timeout SIGNAL to exit the program
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
    msg="${msg:-$(_mf "Operation cancelled")}"
    no_msg="${no_msg:-${msg}}"
    error_msg="${error_msg:-${msg}}"
    exit_msg="${exit_msg:-${msg}}"

    # Determine default behavior based on def_val parameter
    if [[ "$option" == "bool" ]]; then
      no_value="${no_value:-"Y"}" # Default:
      prompt="$prompt $([[ "$no_value" == "Y" ]] && echo "[Y/n]" || echo "[y/N]")"
    elif [[ "$option" == "number" ]]; then
      no_value="${no_value:-0}" # Default: 0
    elif [[ "$option" == "string" ]]; then
      no_value="${no_value:-""}" # Default: blank
    fi

    to_value="${to_value:-${no_value}}" # timeout: default value = no_value
    err_handle="${err_handle:-}"        # default: no error handler

    # Use result_f to store the user's input (only for number | string callback)
    local result_f=$([[ $option != "bool" ]] && generate_temp_file || echo "") # Generate a temp file
    set +e
    (do_confirm_action "$result_f" "$prompt" "$option" "$no_value" "$to_value" "$err_handle" "$error_msg")
    local rc=$?
    set -e

    # echo "ON_EXIT_CODE = $ON_EXIT_CODE"
    if [[ "$rc" -eq 0 ]]; then
      if [[ ${#args[@]} -gt 0 ]]; then
        if [[ $option == "bool" ]]; then
          "${args[@]}"
        else
          "${args[@]}" "$(<"$result_f")"
        fi
        return $?
      fi
    elif [[ "$rc" -eq 1 ]]; then
      warning "$no_msg"
    elif [[ "$rc" -eq 2 || "$rc" -eq 3 ]]; then
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
