#!/bin/bash

# Load once only
if [[ -z "${LOADED_BASH_UTILS:-}" ]]; then
  LOADED_BASH_UTILS=1

  # ==============================================================================
  # Function: error handler
  # Returns:
  #   0 = NO ERROR | NOT EXIST: Error handler does not exist
  #       new_response: The user can return a new response
  #   2 = CONTINUE: to be continued
  #   3 = EXIT: to exit the program
  # ==============================================================================
  error_handler() {
    local result_f="$1" # Temp file to store result
    local response="$2"
    local err_handle="$3"
    local error_msg="$4"

    [[ -z "$err_handle" ]] && return 0 # 0 = no error

    local new_response=$("$err_handle" "$response" "$error_msg")
    local err_code=$(tuple_code "$new_response") # code
    [[ $err_code == 0 ]] || return "$err_code"   # 0 = no error 2 = continue, 3 = exit

    new_response=$(tuple_result "$new_response") # new_response
    if [[ -n "$new_response" ]]; then
      echo "$new_response" >"$result_f" # Update response
    else
      echo "$response" >"$result_f" # Return the response value
    fi
  }

  # Boolean option [YyNn]
  bool_handler() {
    local response="$1"

    if [[ ! "$response" =~ ^[YyNn]$ ]]; then
      string "$MSG_OPER_FAIL_BOOL"
      return 2 # 2 = continue
    fi
    [[ "$response" =~ ^[Yy]$ ]] && return 0 || return 1
  }

  # Number option
  number_handler() {
    local result_f="$1" # Temp file to store result
    local response="$2"
    local err_handle="$3"
    local error_msg="$4"

    if [[ ! "$response" =~ ^[0-9]+$ ]]; then
      string "$MSG_OPER_FAIL_NUMBER"
      return 2 # 2 = continue
    fi

    error_handler "$result_f" "$response" "$err_handle" "$error_msg"
    return $? # 0 = no error 2 = continue, 3 = exit
  }

  # String option
  string_handler() {
    local result_f="$1" # Temp file to store result
    local response="$2"
    local err_handle="$3"
    local error_msg="$4"

    error_handler "$result_f" "$response" "$err_handle" "$error_msg"
    return $? # 0 = no error 2 = continue, 3 = exit
  }

  do_confirm_action() {
    local result_f="${1:-}" # Temp file to store result
    local prompt="$2"
    local option="$3" # "bool" | "number" | "string"
    local no_value="$4"
    local to_value="$5"
    local err_handle="$6"
    local error_msg="$7"

    local last_key_time
    local timeout=$(get_time_out) # 999999=永不超时
    local rc
    local now
    local elapsed
    local start_time
    local key

    trap 'printf "\n" >&2; exit 130' INT # if tty does not show characters, use `stty echo` or `stty sane`
    trap 'printf "\n" >&2; exit 131' QUIT
    trap 'printf "\n" >&2; exit 143' TERM

    while true; do
      response=""
      start_time=$(date +%s)
      clear_input
      printf "%s " "$prompt" >&2

      while true; do
        # Read one character with 0.5s timeout for responsiveness
        last_key_time=0
        read -rsn1 -t 0.5 key
        rc=$?
        now=$(date +%s%3N) # 毫秒
        elapsed=$((now - last_key_time))
        # handle key
        if [[ $rc -eq 0 ]]; then
          if [[ -z "$key" ]]; then # Enter (End of line)
            response=$(return_feedback "$response" "$no_value")
            break

          elif [[ $key == $'\x18' ]]; then # Ctrl+X (timeout toggle)
            if ((elapsed > 250)); then     # 250ms to prevent flickering
              last_key_time=$now
              timeout=$(toggle_time_out)
              start_time=$(date +%s)
              clear_input # Clear input buffer
            fi

          elif [[ $key == $'\x7f' || $key == $'\b' ]]; then # Backspace (ASCII 127 | ASCII 8)
            if ((elapsed > 150)); then                      # 150ms to prevent flickering
              last_key_time=$now
              response=$(safe_backspace "$prompt" "$response")
              [[ -z "$response" ]] && start_time=$(date +%s)
              clear_input # Clear input buffer
            fi

          else # Normal character input
            response+="$key"
            printf "%s" "$key" >&2
          fi

        elif [[ $rc -gt 128 || $rc -eq 142 ]]; then # Check timeout if response is empty
          response=$(check_timeout "$response" "$to_value" "$start_time" "$timeout")
          [[ $? == 0 ]] && break

        elif [[ $rc -eq 1 ]]; then
          break # Ctrl+D (EOF — End Of File)

        else
          printf "\n" >&2
          exit $rc # Exit with the error code
        fi
      done

      # read -t "$timeout" -rp "$prompt " response
      # rc=$?
      # if [[ $rc -eq 0 ]]; then
      # if [[ -z "$response" ]]; then
      #   response=$no_value # set default value
      # else
      #   response="${response// /}" # Remove whitespace characters
      # fi
      # elif [[ $rc -eq 130 ]]; then
      #   return 130 # 被中断
      # elif [[ $rc -gt 128 ]]; then
      #   printf "\n" >&2
      #   response=$to_value # 超时或其他信号 (包括142)
      # else
      #   printf "\n" >&2
      #   exit $rc
      # fi
      if [[ "$option" == "bool" ]]; then
        bool_handler "$response"
      elif [[ "$option" == "number" ]]; then
        number_handler "$result_f" "$response" "$err_handle" "$error_msg"
      elif [[ "$option" == "string" ]]; then
        string_handler "$result_f" "$response" "$err_handle" "$error_msg"
      fi
      rc=$?
      if [[ $rc -eq 2 ]]; then
        printf "\n" >&2
        continue # Continue to prompt again
      else
        exit $rc # Exit the function
      fi
    done

    trap - INT QUIT TERM
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
  #   result_f="temp_file": temporary file to store the result (default: empty)
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
        result_f=*) result_f="${1#result_f=}" ;;
        *) args+=("$1") ;;
      esac
      shift
    done

    # set default messages if not provided
    msg="${msg:-$MSG_OPER_CANCELLED}"
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
    result_f="${result_f:-}" # default: empty
    if [[ $option != "bool" && -z "$result_f" ]]; then
      result_f=$(generate_temp_file) # Generate a temp file
    fi

    local orig_stty=$(stty -g)
    set +e
    (do_confirm_action "$result_f" "$prompt" "$option" "$no_value" "$to_value" "$err_handle" "$error_msg")
    local rc=$?
    clear_input
    set -e
    stty "$orig_stty"

    # echo "ON_EXIT_CODE = $ON_EXIT_CODE"
    if [[ "$rc" -eq 0 ]]; then
      if [[ ${#args[@]} -gt 0 ]]; then
        if [[ $option == "bool" ]]; then
          "${args[@]}"
        else
          "${args[@]}" "$(<"$result_f")" # Read response
        fi
        rc=$?
      fi
    elif [[ "$rc" -eq 1 ]]; then
      warning "$no_msg"
    elif [[ "$rc" -eq 2 || "$rc" -eq 3 ]]; then
      warning "$error_msg"
    elif [[ "$rc" -eq 130 ]]; then
      warning "$exit_msg"
    else
      exiterr "$exit_msg"
    fi
    return $rc
  }

fi
