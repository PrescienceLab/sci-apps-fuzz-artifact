#!/bin/bash
set -euxo pipefail
#
# This script is AI-generated.
# Keep an eye out for bugs.
#
# Usage: ./tag_files.sh application file_list.txt file_classification.json
#

TOP_KEY="$1"
FILE_LIST="$2"
DATA_FILE="$3"

# Hardcoded properties and values
prop1_name="belongs_to"
prop2_name="kind"

prop1_values=(application library unknown)
prop2_values=(parser non-parser combined unknown)

# Ensure JSON data file exists and has an object
if [ ! -f "$DATA_FILE" ]; then
  echo "{}" > "$DATA_FILE"
fi

# Ensure top-level key exists and is an object
tmp="$(mktemp)"
jq --arg k "$TOP_KEY" '
  . as $root
  | if has($k) then . else . + {($k): {}} end
' "$DATA_FILE" > "$tmp"
mv "$tmp" "$DATA_FILE"

choose_from() {
  local options=("$@")

  PS3="> "
  select opt in "${options[@]}"; do
    if [[ -n "$opt" ]]; then
      echo "$opt"
      break
    fi
  done < /dev/tty
}

canonpath() {
    # Usage: canonpath PATH
    # Canonicalizes ".", ".." and symlinks
    # If PATH is relative, result stays relative.
    local in="$1"
    local abs

    # Get canonical absolute path.
    abs=$(realpath -m -- "$in") || return 1

    # If input was relative and resolved path is under $PWD, strip $PWD.
    if [[ "$in" != /* ]]; then
        case "$abs" in
            "$PWD")          printf '%s\n' "." ;;
            "$PWD"/*)        printf '%s\n' "${abs#"$PWD"/}" ;;
            *)               printf '%s\n' "$abs" ;;
        esac
    else
        printf '%s\n' "$abs"
    fi
}

while IFS= read -r filename || [ -n "$filename" ]; do
  # Skip empty lines
  [ -z "$filename" ] && continue

  if jq -e "."$TOP_KEY" | has(\"$filename\")" "$DATA_FILE" >/dev/null 2>&1; then
    continue
  fi

  canon_filename="$(canonpath $filename)"
  FILES="$(find . -type f -regex ".*/$canon_filename")"
  # Open file with nvim and wait for exit
  echo $FILES
  nvim -p $FILES

  echo
  echo "File: $filename"
  echo "Choose value for $prop1_name:"
  val1="$(choose_from "${prop1_values[@]}")"

  echo
  echo "Choose value for $prop2_name:"
  val2="$(choose_from "${prop2_values[@]}")"

  # Update JSON: under .TOP_KEY add/overwrite entry for this filename
  tmp="$(mktemp)"
  jq \
    --arg top "$TOP_KEY" \
    --arg fname "$filename" \
    --arg p1 "$prop1_name" \
    --arg p2 "$prop2_name" \
    --arg v1 "$val1" \
    --arg v2 "$val2" \
    '
    .[$top][$fname] = {
      ($p1): $v1,
      ($p2): $v2
    }
    ' "$DATA_FILE" > "$tmp"
  mv "$tmp" "$DATA_FILE"

  echo "Updated $DATA_FILE for \"$filename\"."
  echo
done < "$FILE_LIST"

