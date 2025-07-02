#!/bin/bash

# Load once only
if [[ -z "${LOADED_BASH_UTILS:-}" ]]; then
  LOADED_BASH_UTILS=1

  # ==============================================================================
  # Confirmation function with callback
  # Parameters:
  #   $1: prompt message
  #   $2+: callback function name and its arguments
  # Optional parameters:
  #   msg="text": custom cancel message (default: "operation is cancelled")
  #   default="y|n": default value for empty input (default: "y")
  # Returns:
  #   callback function's return value, or 2 when cancelled
  # ==============================================================================
  confirm_action() {
    local prompt="$1"
    shift

    # Parse optional parameters
    local cancel_msg=""
    local def_val="y" # Default: empty input means Yes
    local args=()
    while [[ $# -gt 0 ]]; do
      case "$1" in
        msg=*)
          cancel_msg="${1#msg=}"
          ;;
        default=*)
          def_val="${1#default=}"
          ;;
        *)
          args+=("$1")
          ;;
      esac
      shift
    done

    # Set default cancel message
    if [[ -z "$cancel_msg" ]]; then
      cancel_msg=$(_mf "operation is cancelled")
    fi

    # Determine default behavior based on def_val parameter
    local default_prompt="[Y/n]"
    if [[ "$def_val" =~ ^[Nn]$ ]]; then
      # If def_val=n, empty input means No
      default_prompt="[y/N]"
    fi

    # User Exit on Ctrl+C
    # shellcheck disable=SC2317
    do_keyboard_interrupt() {
      echo ""
      exiterr "operation is cancelled"
    }

    trap do_keyboard_interrupt INT # Exit directly on Ctrl+C

    while true; do
      read -p "$prompt $default_prompt " response
      if [[ -z "$response" || "$response" =~ ^[YyNn]$ ]]; then
        break
      else
        error "Please enter 'y' for yes, 'n' for no, or press Enter for default"
      fi
    done

    trap - INT # Remove SIGINT signal handler

    local result=0 # user enter Y or y
    if [[ -z "$response" && "$def_val" =~ ^[Nn]$ ]]; then
      result=1
    elif [[ "$response" =~ ^[Nn]$ ]]; then
      result=1
    fi

    if [[ "$result" -eq 0 ]]; then
      "${args[@]}" # 👈 callback=$1, args=other parameter
      return $?    # Return callback's exit code
    else
      warning "$cancel_msg"
      return $result
    fi
  }

fi
