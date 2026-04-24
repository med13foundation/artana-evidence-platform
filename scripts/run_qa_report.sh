#!/usr/bin/env bash

# Run the full QA suite with a structured final warnings/errors report.

set -euo pipefail

MAKE_BIN="${MAKE_BIN:-make}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REPORT_DIR="${REPORT_DIR:-reports}"
TIMESTAMP="${TIMESTAMP:-$(date +%Y%m%d_%H%M%S)}"
QA_REPORT="${QA_REPORT:-$REPORT_DIR/qa_report_${TIMESTAMP}.txt}"

mkdir -p "$REPORT_DIR"
: > "$QA_REPORT"

echo "=========================================" > "$QA_REPORT"
echo "Artana Evidence Platform - QA Report" >> "$QA_REPORT"
echo "Generated: $(date)" >> "$QA_REPORT"
echo "=========================================" >> "$QA_REPORT"

WARN_PATTERN="(⚠️|⚠|warning|warn|deprecat|deprecated)"
ERROR_PATTERN="(fatal|failure|failed|traceback|exception|SyntaxError|TypeError|ValueError|ModuleNotFoundError|npm ERR!|\\bFAILED\\b|\\bFail(ed|ure)?\\b|⨯|❌|\\berror\\b)"

declare -a STEP_NAMES
declare -a STEP_SECTIONS
declare -a STEP_RESULTS
declare -a STEP_WARN_COUNTS
declare -a STEP_ERROR_COUNTS
declare -a STEP_LOGS
FAILING_STEP=""

run_step() {
    local section="$1"
    local name="$2"
    local command="$3"
    local log_file="$REPORT_DIR/qa_step_${name}.log"
    local warn_count=0
    local error_count=0
    local status="PASS"

    STEP_NAMES+=("$name")
    STEP_SECTIONS+=("$section")
    STEP_LOGS+=("$log_file")

    {
        echo ""
        echo "=================================================="
        echo "SECTION: $section"
        echo "STEP: $name"
        echo "COMMAND: $command"
        echo "=================================================="
    } | tee -a "$QA_REPORT"

    set +e
    bash -c "set -o pipefail; $command" 2>&1 | tee "$log_file" | tee -a "$QA_REPORT"
    local step_status=${PIPESTATUS[0]}
    set -e

    local analysis_log="$REPORT_DIR/qa_step_${name}_analysis.log"
    : > "$analysis_log"

    if [ -s "$log_file" ]; then
        grep -Eiv \
            "^(=+|SECTION:|STEP:|COMMAND:|STEP RESULT:|Detected warnings:|Detected errors:|Warnings detected:|Errors detected:|Overall Result:|### )" \
            "$log_file" \
            | grep -Eiv "^\s*(warnings|errors)\s*=\s*[0-9]+\s*,\s*(errors|warnings)\s*=\s*[0-9]+\s*$" \
            | grep -Eiv "^\s*Warnings:\s*[0-9]+\s*$" \
            | grep -Eiv "^\s*Errors:\s*[0-9]+\s*$" \
            | grep -Eiv "^\s*⨯\s+devtoolSegmentExplorer\s*$" \
            | grep -Eiv -- "--(disable-error-code|show-error-codes)\b" \
            > "$analysis_log" || true

        warn_count=$(grep -Eic "$WARN_PATTERN" "$analysis_log" || true)
        error_count=$(grep -Eic "$ERROR_PATTERN" "$analysis_log" || true)
    fi

    if [ "$step_status" -ne 0 ]; then
        status="FAIL"
        FAILING_STEP="$name"
    fi

    STEP_RESULTS+=("$status")
    STEP_WARN_COUNTS+=("$warn_count")
    STEP_ERROR_COUNTS+=("$error_count")

    {
        echo "STEP RESULT: $status"
        echo "Detected warnings: $warn_count | Detected errors: $error_count"
        echo ""
    } | tee -a "$QA_REPORT"

    if [ "$status" = "FAIL" ]; then
        echo ""
        echo "❌ Step '$name' failed. QA run stopped to keep fail-fast behavior."
        echo "💥 See step log: $log_file"
        return 1
    fi

    return 0
}

print_issue_block() {
    local step_name="$1"
    local issue_type="$2"
    local pattern="$3"
    local log_file="$4"
    local heading="$5"
    local lines

    if [ ! -f "$log_file" ]; then
        return
    fi

    local analysis_log="${log_file%.log}_analysis.log"
    if [ -f "$analysis_log" ]; then
        log_file="$analysis_log"
    fi

    lines="$(grep -Eim 1 "$pattern" "$log_file" || true)"
    if [ -z "$lines" ]; then
        return
    fi

    echo ""
    echo "$heading for $issue_type in $step_name:"
    echo "  $step_name"
    grep -Ei "$pattern" "$log_file" | sed -n '1,8p' | sed 's/^/   - /'
}

run_all_steps() {
    local -a steps=(
        "Backend|service-checks|${MAKE_BIN} service-checks"
    )

    local entry
    local step_status=0
    set +e
    for entry in "${steps[@]}"; do
        IFS='|' read -r section name command <<< "$entry"
        run_step "$section" "$name" "$command"
        step_status=$?
        if [ $step_status -ne 0 ]; then
            break
        fi
    done
    set -e
}

run_all_steps

run_status="PASS"
overall_warnings=0
overall_errors=0

{
    echo ""
    echo "========================================="
    echo "FINAL QA REPORT"
    echo "========================================="
    if [ -z "$FAILING_STEP" ]; then
        echo "Overall Result: ✅ PASS"
    else
        echo "Overall Result: ❌ FAIL (first failing step: $FAILING_STEP)"
        run_status="FAIL"
    fi
} | tee -a "$QA_REPORT"

for idx in "${!STEP_NAMES[@]}"; do
    overall_warnings=$((overall_warnings + STEP_WARN_COUNTS[idx]))
    overall_errors=$((overall_errors + STEP_ERROR_COUNTS[idx]))
done

echo "Warnings detected: $overall_warnings" | tee -a "$QA_REPORT"
echo "Errors detected: $overall_errors" | tee -a "$QA_REPORT"

echo "" | tee -a "$QA_REPORT"
for section in "Backend"; do
    echo "### $section" | tee -a "$QA_REPORT"
    for idx in "${!STEP_NAMES[@]}"; do
        if [ "${STEP_SECTIONS[idx]}" != "$section" ]; then
            continue
        fi
        echo " - ${STEP_NAMES[idx]}: ${STEP_RESULTS[idx]} " | tee -a "$QA_REPORT"
        echo "   warnings=${STEP_WARN_COUNTS[idx]}, errors=${STEP_ERROR_COUNTS[idx]}" | tee -a "$QA_REPORT"
    done
done

echo "" | tee -a "$QA_REPORT"
echo "Detailed issue extract (backend summary):" | tee -a "$QA_REPORT"

for idx in "${!STEP_NAMES[@]}"; do
    step_name="${STEP_NAMES[idx]}"
    log_file="${STEP_LOGS[idx]}"
    print_issue_block "$step_name" "Warnings" "$WARN_PATTERN" "$log_file" "Warnings" | tee -a "$QA_REPORT"
    print_issue_block "$step_name" "Errors" "$ERROR_PATTERN" "$log_file" "Errors" | tee -a "$QA_REPORT"
done

echo ""
echo "Full output and step logs are saved to:" | tee -a "$QA_REPORT"
for idx in "${!STEP_LOGS[@]}"; do
    echo " - ${STEP_LOGS[idx]}" | tee -a "$QA_REPORT"
done
echo "Report saved to: $QA_REPORT" | tee -a "$QA_REPORT"

if [ "$run_status" = "FAIL" ]; then
    echo "⚠️  QA report written to: $QA_REPORT"
    exit 1
fi

echo "✅ QA report written to: $QA_REPORT"
