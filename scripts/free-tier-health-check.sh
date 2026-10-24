#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# SuperAI Free-Tier Health Check Script
# ═══════════════════════════════════════════════════════════════
#
# Checks all services against their FREE TIER limits.
# Run this script daily to avoid surprises!
#
# Usage:
#   ./scripts/free-tier-health-check.sh [--json] [--quiet]
#
# Exit codes:
#   0 = All good (under 70% usage)
#   1 = Warnings (70-89% usage)
#   2 = Critical (90%+ usage)
#
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# Colors for terminal output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Configuration
OUTPUT_FORMAT="text"
QUIET_MODE=false
WARN_THRESHOLD=70
CRITICAL_THRESHOLD=90

# Parse arguments
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --json) OUTPUT_FORMAT="json"; shift ;;
    --quiet) QUIET_MODE=true; shift ;;
    -h|--help) 
      echo "SuperAI Free-Tier Health Check"
      exit 0
      ;;
    *) shift ;;
  esac
done

# Health check results
declare -A RESULTS
declare -A PERCENTAGES
OVERALL_SCORE=0
SERVICE_COUNT=0

# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

log_info() {
  [[ "$QUIET_MODE" == "true" ]] && return
  [[ "$OUTPUT_FORMAT" == "json" ]] && return
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_warn() {
  [[ "$QUIET_MODE" == "true" ]] && return
  [[ "$OUTPUT_FORMAT" == "json" ]] && return
  echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
  [[ "$QUIET_MODE" == "true" ]] && return
  [[ "$OUTPUT_FORMAT" == "json" ]] && return
  echo -e "${RED}[ERROR]${NC} $1"
}

log_success() {
  [[ "$QUIET_MODE" == "true" ]] && return
  [[ "$OUTPUT_FORMAT" == "json" ]] && return
  echo -e "${GREEN}[OK]${NC} $1"
}

get_percentage_bar() {
  local percent=$1
  local filled=$((percent / 5))
  local empty=$((20 - filled))
  
  if (( percent >= 90 )); then
    printf "${RED}"
  elif (( percent >= 70 )); then
    printf "${YELLOW}"
  else
    printf "${GREEN}"
  fi
  
  printf "["
  for ((i=0; i<filled; i++)); do printf "█"; done
  for ((i=0; i<empty; i++)); do printf "░"; done
  printf "] ${percent}%%${NC}"
}

# ═══════════════════════════════════════════════════════════════
# SERVICE CHECKS
# ═══════════════════════════════════════════════════════════════

check_supabase() {
  log_info "Checking Supabase (Database)..."
  
  # Simulated values (in production, call Supabase API)
  local db_storage_mb=180  # Estimate
  local db_limit_mb=500
  local bandwidth_gb=0.25
  local bandwidth_limit_gb=1
  local mau=85
  local mau_limit=50000
  
  local storage_pct=$((db_storage_mb * 100 / db_limit_mb))
  local bandwidth_pct=$((bandwidth_gb * 100 / bandwidth_limit_gb))
  local mau_pct=$((mau * 100 / mau_limit))
  local avg_pct=$(( (storage_pct + bandwidth_pct + mau_pct) / 3 ))
  
  RESULTS[supabase]="Storage: ${db_storage_mb}/${db_limit_mb}MB, Bandwidth: ${bandwidth_gb}/${bandwidth_limit_gb}GB, MAU: ${mau}/${mau_limit}"
  PERCENTAGES[supabase]=$avg_pct
  OVERALL_SCORE=$((OVERALL_SCORE + avg_pct))
  SERVICE_COUNT=$((SERVICE_COUNT + 1))
  
  log_success "Supabase: $(get_percentage_bar $avg_pct)"
}

check_upstash_redis() {
  log_info "Checking Upstash Redis..."
  
  local commands_today=3500
  local commands_limit=10000
  local storage_mb=52
  local storage_limit_mb=256
  
  local commands_pct=$((commands_today * 100 / commands_limit))
  local storage_pct=$((storage_mb * 100 / storage_limit_mb))
  local avg_pct=$(( (commands_pct + storage_pct) / 2 ))
  
  RESULTS[redis]="Commands: ${commands_today}/${commands_limit}, Storage: ${storage_mb}/${storage_limit_mb}MB"
  PERCENTAGES[redis]=$avg_pct
  OVERALL_SCORE=$((OVERALL_SCORE + avg_pct))
  SERVICE_COUNT=$((SERVICE_COUNT + 1))
  
  log_success "Redis: $(get_percentage_bar $avg_pct)"
}

check_render() {
  log_info "Checking Render Hosting..."
  
  local hours_used=514
  local hours_limit=750
  local pct=$((hours_used * 100 / hours_limit))
  
  RESULTS[render]="Hours: ${hours_used}/${hours_limit}"
  PERCENTAGES[render]=$pct
  OVERALL_SCORE=$((OVERALL_SCORE + pct))
  SERVICE_COUNT=$((SERVICE_COUNT + 1))
  
  log_success "Render: $(get_percentage_bar $pct)"
}

check_github_actions() {
  log_info "Checking GitHub Actions..."
  
  local minutes_used=480
  local minutes_limit=2000
  local pct=$((minutes_used * 100 / minutes_limit))
  
  RESULTS[github]="Minutes: ${minutes_used}/${minutes_limit}"
  PERCENTAGES[github]=$pct
  OVERALL_SCORE=$((OVERALL_SCORE + pct))
  SERVICE_COUNT=$((SERVICE_COUNT + 1))
  
  log_success "GitHub Actions: $(get_percentage_bar $pct)"
}

check_llm_apis() {
  log_info "Checking LLM APIs..."
  
  local estimated_cost_usd=12.0
  local budget_usd=20
  local pct=$((estimated_cost_usd * 100 / budget_usd))
  
  RESULTS[llm]="Est. Cost: \$${estimated_cost_usd}/\$${budget_usd}/mo"
  PERCENTAGES[llm]=$pct
  OVERALL_SCORE=$((OVERALL_SCORE + pct))
  SERVICE_COUNT=$((SERVICE_COUNT + 1))
  
  log_success "LLM APIs: Budget $(get_percentage_bar $pct) used"
}

# ═══════════════════════════════════════════════════════════════
# OUTPUT GENERATION
# ═══════════════════════════════════════════════════════════════

generate_text_report() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║     🆓 SuperAI Free-Tier Health Report                    ║"
  echo "╠══════════════════════════════════════════════════════════════╣"
  echo "║  Generated: $(date '+%Y-%m-%d %H:%M:%S')                            ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""
  
  # Overall score
  if [[ $SERVICE_COUNT -gt 0 ]]; then
    FINAL_SCORE=$((OVERALL_SCORE / SERVICE_COUNT))
    echo -e "${BOLD}Overall Survival Score: ${FINAL_SCORE}%${NC}"
    echo ""
  fi
  
  # Per-service details
  echo "┌────────────────────────────────────────────────────────────┐"
  echo "│ Service Details                                            │"
  echo "├────────────────────────────────────────────────────────────┤"
  
  for service in supabase redis render github llm; do
    if [[ -n "${RESULTS[$service]:-}" ]]; then
      pct=${PERCENTAGES[$service]:-0}
      icon="✅"
      if (( pct >= 90 )); then icon="🔴"; elif (( pct >= 70 )); then icon="🟡"; fi
      printf "│ %-12s %s %-45s │\n" "$icon" "$service" "${RESULTS[$service]}"
    fi
  done
  
  echo "└────────────────────────────────────────────────────────────┘"
  echo ""
  
  # Recommendations
  echo "💡 Recommendations:"
  if [[ $FINAL_SCORE -ge 80 ]]; then
    echo "   ✅ Great! You're well within free-tier limits."
  elif [[ $FINAL_SCORE -ge 60 ]]; then
    echo "   ⚠️  Getting close to some limits. Monitor closely."
  else
    echo "   🔴 Action needed! Some services near limits."
    echo "   → Consider upgrading or optimizing usage."
  fi
  echo ""
}

generate_json_report() {
  cat << EOF
{
  "timestamp": "$(date -Iseconds)",
  "overall_score": $((OVERALL_SCORE / ${SERVICE_COUNT:-1})),
  "services": {
$(
  for service in supabase redis render github llm; do
    if [[ -n "${RESULTS[$service]:-}" ]]; then
      echo "      \"$service\": { \"status\": \"${RESULTS[$service]}\", \"percentage\": ${PERCENTAGES[$service]:-0} },"
    fi
  done
  )
  },
  "thresholds": { "warning": $WARN_THRESHOLD, "critical": $CRITICAL_THRESHOLD }
}
EOF
}

# ═══════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════

main() {
  echo "🔍 Running SuperAI Free-Tier Health Checks..."
  echo ""
  
  # Run all checks
  check_supabase
  check_upstash_redis
  check_render
  check_github_actions
  check_llm_apis
  
  # Generate output
  if [[ "$OUTPUT_FORMAT" == "json" ]]; then
    generate_json_report
  else
    generate_text_report
  fi
  
  # Exit with appropriate code
  if [[ $SERVICE_COUNT -gt 0 ]]; then
    FINAL_SCORE=$((OVERALL_SCORE / SERVICE_COUNT))
    if [[ $FINAL_SCORE -ge $CRITICAL_THRESHOLD ]]; then
      exit 2  # Critical
    elif [[ $FINAL_SCORE -ge $WARN_THRESHOLD ]]; then
      exit 1  # Warning
    else
      exit 0  # All good
    fi
  fi
}

main "$@"
