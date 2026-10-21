#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compiler=${CC:-cc}
temporary_dir=$(mktemp -d)
trap 'rm -rf "$temporary_dir"' EXIT HUP INT TERM

source_path=
pristine_source_path=
while [ "$#" -gt 0 ]; do
	case "$1" in
	--source)
		[ "$#" -ge 2 ] || { echo "--source requires a path" >&2; exit 2; }
		source_path=$2
		shift 2
		;;
	--pristine-source)
		[ "$#" -ge 2 ] || { echo "--pristine-source requires a path" >&2; exit 2; }
		pristine_source_path=$2
		shift 2
		;;
	*)
		echo "usage: $0 --source PATCHED_RES_AUDIOSOCKET_C [--pristine-source RES_AUDIOSOCKET_C]" >&2
		exit 2
		;;
	esac
done

if [ -z "$source_path" ]; then
	echo "source comparison is required; pass --source with the patched res_audiosocket.c" >&2
	exit 2
fi
[ -r "$source_path" ] || { echo "cannot read patched source: $source_path" >&2; exit 2; }

if [ -z "$pristine_source_path" ]; then
	pristine_dir="$temporary_dir/pristine"
	mkdir -p "$pristine_dir/res"
	cp "$source_path" "$pristine_dir/res/res_audiosocket.c"
	(
		cd "$pristine_dir"
		patch --fuzz=0 -R -p1 < "$script_dir/res_audiosocket-21.10.2-header-read.patch" >/dev/null
	)
	pristine_source_path="$pristine_dir/res/res_audiosocket.c"
else
	[ -r "$pristine_source_path" ] || {
		echo "cannot read pristine source: $pristine_source_path" >&2
		exit 2
	}
fi

python3 - "$script_dir/test-res-audiosocket-header-read.c" "$pristine_source_path" "$source_path" <<'PY'
import hashlib
import re
import sys

harness_path, pristine_path, patched_path = sys.argv[1:]
expected_pristine_sha256 = "a9ff97eca61dad09148ccb67de5584c0c6854d8cc748f916d6585d055f6c62da"

with open(harness_path, encoding="utf-8") as stream:
	 h = stream.read()
with open(pristine_path, encoding="utf-8") as stream:
	 pristine = stream.read()
with open(patched_path, encoding="utf-8") as stream:
	 patched = stream.read()

actual_pristine_sha256 = hashlib.sha256(pristine.encode()).hexdigest()
if actual_pristine_sha256 != expected_pristine_sha256:
	raise SystemExit(
		"pinned pristine source hash mismatch: " + actual_pristine_sha256
	)

def extract_function(text, function_name):
	declaration = "struct ast_frame *" + function_name + "("
	start = text.index(declaration)
	brace = text.index("{", start)
	depth = 0
	quote = None
	escaped = False
	line_comment = False
	block_comment = False
	for index in range(brace, len(text)):
		char = text[index]
		next_char = text[index + 1] if index + 1 < len(text) else ""
		if line_comment:
			if char == "\n":
				line_comment = False
		elif block_comment:
			if char == "*" and next_char == "/":
				block_comment = False
		elif quote:
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == quote:
				quote = None
		elif char in "\"'":
			quote = char
		elif char == "/" and next_char == "/":
			line_comment = True
		elif char == "/" and next_char == "*":
			block_comment = True
		elif char == "{":
			depth += 1
		elif char == "}":
			depth -= 1
			if depth == 0:
				return text[start:index + 1]
	raise SystemExit("unterminated AudioSocket receive function")

def marked_function(text, marker, function_name):
	begin = text.index("/* BEGIN_" + marker + "_FUNCTION */")
	end = text.index("/* END_" + marker + "_FUNCTION */", begin)
	return extract_function(text[begin:end], function_name)

def normalize(function_text, renamed_name):
	return re.sub(
		r"\b" + re.escape(renamed_name) + r"\b",
		"ast_audiosocket_receive_frame_with_hangup",
		function_text.replace("\r\n", "\n"),
	)

checks = (
	("PINNED_BASELINE", "baseline_receive_frame_with_hangup", pristine),
	("PATCHED", "patched_receive_frame_with_hangup", patched),
)
for marker, renamed_name, source in checks:
	actual = marked_function(h, marker, renamed_name)
	expected = extract_function(source, "ast_audiosocket_receive_frame_with_hangup")
	if normalize(actual, renamed_name) != expected.replace("\r\n", "\n"):
		raise SystemExit(marker.lower() + " receive function drifted from pinned source")

print("AudioSocket source/body guard passed (pinned pristine hash and both functions match)")
PY

"$compiler" \
	-std=c11 \
	-Wall \
	-Wextra \
	-Werror \
	-pthread \
	"$script_dir/test-res-audiosocket-header-read.c" \
	-o "$temporary_dir/test-res-audiosocket-header-read"

"$temporary_dir/test-res-audiosocket-header-read" baseline
"$temporary_dir/test-res-audiosocket-header-read" patched
