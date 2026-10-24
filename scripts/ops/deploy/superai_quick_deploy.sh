#!/bin/bash
#
#================================================================================
# SuperAI Quick Deploy - One-Click Deployment Script
#================================================================================
# 🚀 Automated deployment for SuperAI platform
# 🔧 Handles: dependencies, environment, patches, builds, and services
# ✅ Pre-flight checks, health verification, rollback support
#
# Author: SuperAI Toolkit
# Version: 1.0.0
# License: MIT
#
# Usage:
#   ./superai_quick_deploy.sh                  # Full deployment
#   ./superai_quick_deploy.sh --setup           # Initial setup only
#   ./superai_quick_deploy.sh --patches         # Apply SuperAI patches
#   ./superai_quick_deploy.sh --build           # Build frontend + backend
#   ./superai_quick_deploy.sh --deploy          # Deploy to production
#   ./superai_quick_deploy.sh --rollback        # Rollback last deployment
#   ./superai_quick_deploy.sh --status          # Check deployment status
#   ./superai_quick_deploy.sh --backup          # Create backup before deploy
#
# CPU Impact of This Script:
#   - Setup/Install: High CPU during npm install (~30s) and pip install (~20s)
#   - Build: Very high CPU during Next.js build (~2-5 min)
#   - Patch application: Negligible (file copies)
#   - Service restart: Brief spike (<5s)
#   - Total: ~10-15% CPU over 5-10 minutes (mostly build time)
#================================================================================

set -e  # Exit on error

#================================================================================
# CONFIGURATION
#================================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Version tracking
SUPERAI_VERSION="1.0.0"
DEPLOY_LOG="$PROJECT_ROOT/deploy.log"
BACKUP_DIR="$PROJECT_ROOT/backups"
ROLLBACK_DIR="$PROJECT_ROOT/rollbacks"

# Default settings
SKIP_TESTS=false
SKIP_BUILD=false
APPLY_PATCHES=true
CREATE_BACKUP=true
DEPLOY_ENV="production"

#================================================================================
# UTILITY FUNCTIONS
#================================================================================

log() {
    local level=$1; shift
    local message=$*
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    echo -e "[$timestamp] [$level] $message" | tee -a "$DEPLOY_LOG"
    
    case $level in
        INFO)    echo -e "${GREEN}✅ $message${NC}" ;;
        WARN)    echo -e "${YELLOW}⚠️  $message${NC}" ;;
        ERROR)   echo -e "${RED}❌ $message${NC}" ;;
        ACTION)  echo -e "${CYAN}🔧 $message${NC}" ;;
        *)       echo "$message" ;;
    esac
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log ERROR "Required command not found: $1"
        return 1
    fi
    return 0
}

check_success() {
    if [ $? -eq 0 ]; then
        log INFO "$1"
    else
        log ERROR "$1 failed!"
        exit 1
    fi
}

confirm() {
    if [ "$FORCE" = true ]; then
        return 0
    fi
    
    read -p "$(echo -e ${YELLOW}$1 [y/N]: ${NC})" response
    [[ "$response" =~ ^[Yy]$ ]]
}

create_dirs() {
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$ROLLBACK_DIR"
    mkdir -p "$PROJECT_ROOT/logs"
}

#================================================================================
# PRE-FLIGHT CHECKS
#================================================================================

preflight_checks() {
    log ACTION "Running pre-flight checks..."
    
    local errors=0
    
    # Check required commands
    local required_commands=("node" "npm" "python3" "git")
    
    for cmd in "${required_commands[@]}"; do
        if check_command "$cmd"; then
            local version=$($cmd --version 2>/dev/null | head -1)
            log INFO "✓ $cmd: $version"
        else
            ((errors++))
        fi
    done
    
    # Check Node.js version (need 18+)
    local node_version=$(node -v | sed 's/v//')
    local node_major=$(echo $node_version | cut -d. -f1)
    
    if [ "$node_major" -lt 18 ]; then
        log ERROR "Node.js version must be >= 18 (found: $node_version)"
        ((errors++))
    fi
    
    # Check Python version (need 3.9+)
    local python_version=$(python3 --version 2>/dev/null | awk '{print $2}')
    local python_major=$(echo $python_version | cut -d. -f1)
    local python_minor=$(echo $python_version | cut -d. -f2)
    
    if [ "$python_major" -lt 3 ] || ([ "$python_major" -eq 3 ] && [ "$python_minor" -lt 9 ]); then
        log ERROR "Python version must be >= 3.9 (found: $python_version)"
        ((errors++))
    fi
    
    # Check disk space (need at least 2GB free)
    local free_space=$(df -BG "$PROJECT_ROOT" | tail -1 | awk '{print $4}' | sed 's/G//')
    if [ "$free_space" -lt 2 ]; then
        log ERROR "Insufficient disk space (need 2GB+, have ${free_space}GB)"
        ((errors++))
    else
        log INFO "✓ Disk space: ${free_space}GB available"
    fi
    
    # Check memory (need at least 2GB)
    local total_mem=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}' || echo "unknown")
    if [ "$total_mem" != "unknown" ] && [ "$total_mem" -lt 2 ]; then
        log WARN "Low memory detected (${total_mem}GB). Build may fail."
    fi
    
    # Check .env file
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        if [ -f "$PROJECT_ROOT/.env.example" ]; then
            log WARN ".env file missing. Creating from .env.example..."
            cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
            log ERROR "Please edit .env with your configuration before deploying."
            ((errors++))
        else
            log ERROR ".env file not found and no .env.example available"
            ((errors++))
        fi
    else
        log INFO "✓ .env file exists"
    fi
    
    # Check git status (warn if uncommitted changes)
    if git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree &>/dev/null; then
        local changes=$(git -C "$PROJECT_ROOT" status --porcelain 2>/dev/null | wc -l)
        if [ "$changes" -gt 0 ]; then
            log WARN "$changes uncommitted change(s) in repository"
        else
            log INFO "✓ Git working tree clean"
        fi
    fi
    
    if [ $errors -gt 0 ]; then
        log ERROR "Pre-flight checks failed with $errors error(s)"
        exit 1
    fi
    
    log INFO "Pre-flight checks passed! ✓"
}

#================================================================================
# SETUP & DEPENDENCIES
#================================================================================

setup_dependencies() {
    log ACTION "Installing dependencies..."
    
    # Node.js dependencies
    log INFO "Installing Node.js packages..."
    cd "$PROJECT_ROOT"
    
    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules" ]; then
        npm install --legacy-peer-deps
        check_success "npm install"
    else
        log INFO "Node.js dependencies up to date"
    fi
    
    # Python dependencies
    log INFO "Installing Python packages..."
    cd "$PROJECT_ROOT/backend" 2>/dev/null || cd "$PROJECT_ROOT"
    
    if [ -f "requirements.txt" ]; then
        python3 -m venv venv 2>/dev/null || true
        
        if [ -f "venv/bin/activate" ]; then
            source venv/bin/activate
            pip install -r requirements.txt -q
            check_success "pip install"
        else
            log WARN "Could not create Python virtual environment"
            pip install -r requirements.txt -q 2>/dev/null || \
                pip3 install -r requirements.txt -q 2>/dev/null || \
                log ERROR "Failed to install Python dependencies"
        fi
    else
        log WARN "No requirements.txt found"
    fi
    
    cd "$PROJECT_ROOT"
}

#================================================================================
# PATCH APPLICATION
#================================================================================

apply_superai_patches() {
    if [ "$APPLY_PATCHES" = false ]; then
        log INFO "Patch application skipped (--no-patches)"
        return
    fi
    
    log ACTION "Applying SuperAI transformation patches..."
    
    local patch_dir="$SCRIPT_DIR/patches"
    local unified_patch="$SCRIPT_DIR/supremeai_superapi_patch.diff"
    
    # Check if transform script exists
    if [ -f "$SCRIPT_DIR/superai_transform.py" ]; then
        log INFO "Using superai_transform.py for automated patching..."
        
        cd "$PROJECT_ROOT"
        python3 "$SCRIPT_DIR/superai_transform.py" --yes
        check_success "SuperAI transformation"
        
    elif [ -f "$unified_patch" ]; then
        log INFO "Applying unified patch..."
        
        cd "$PROJECT_ROOT"
        
        # Try to apply the patch
        if git apply --check "$unified_patch" 2>/dev/null; then
            git apply "$unified_patch"
            check_success "Patch application"
        else
            log WARN "Git apply failed, trying with patch command..."
            
            # Backup first
            cp -r "$PROJECT_ROOT/backend" "$ROLLBACK_DIR/pre_patch_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
            
            patch -p1 < "$unified_patch" || {
                log ERROR "Manual intervention may be required for patching"
                log INFO "Individual patches available in: $patch_dir"
                return 1
            }
        fi
        
    elif [ -d "$patch_dir" ] && [ "$(ls -A $patch_dir)" ]; then
        log INFO "Applying individual patches..."
        
        for patch_file in "$patch_dir"/*.diff; do
            if [ -f "$patch_file" ]; then
                log INFO "Applying: $(basename $patch_file)"
                
                cd "$PROJECT_ROOT"
                patch -p1 < "$patch_file" 2>/dev/null && \
                    log INFO "✓ Applied: $(basename $patch_file)" || \
                    log WARN "✗ Skipped: $(basename $patch_file)"
            fi
        done
    else
        log WARN "No patches found. Download SuperAI patches for optimization features."
    fi
    
    # Verify critical files exist after patching
    local critical_files=(
        "backend/core/cache.py"
        "backend/core/rate_limit.py"
        "backend/core/monitoring.py"
    )
    
    local found=0
    for file in "${critical_files[@]}"; do
        if [ -f "$PROJECT_ROOT/$file" ]; then
            ((found++))
        fi
    done
    
    log INFO "Patches applied: $found/${#critical_files[@]} core modules installed"
}

#================================================================================
# BUILD PROCESS
#================================================================================

build_frontend() {
    if [ "$SKIP_BUILD" = true ]; then
        log INFO "Frontend build skipped (--skip-build)"
        return
    fi
    
    log ACTION "Building Next.js frontend..."
    cd "$PROJECT_ROOT"
    
    # Clean previous build
    rm -rf .next 2>/dev/null || true
    
    # Production build
    export NODE_ENV=production
    
    # Run build with memory optimization for low-resource systems
    NODE_OPTIONS="--max-old-space-size=4096" npm run build
    
    check_success "Next.js build"
    
    log INFO "Frontend built successfully ✓"
}

build_backend() {
    log ACTION "Preparing backend..."
    cd "$PROJECT_ROOT/backend" 2>/dev/null || cd "$PROJECT_ROOT"
    
    # Compile TypeScript if needed
    if [ -f "tsconfig.json" ] && check_command "tsc"; then
        npx tsc --noEmit 2>/dev/null && log INFO "TypeScript compilation OK" || \
            log WARN "TypeScript warnings found (non-blocking)"
    fi
    
    # Collect static files if needed
    if [ -f "manage.py" ]; then
        python manage.py collectstatic --noinput 2>/dev/null || true
    fi
    
    log INFO "Backend ready ✓"
}

run_tests() {
    if [ "$SKIP_TESTS" = true ]; then
        log INFO "Tests skipped (--skip-tests)"
        return
    fi
    
    log ACTION "Running tests..."
    cd "$PROJECT_ROOT"
    
    # Frontend tests
    if grep -q '"test"' package.json 2>/dev/null; then
        npm test -- --passWithNoTests 2>/dev/null && \
            log INFO "Frontend tests passed" || \
            log WARN "Frontend tests failed (continuing...)"
    fi
    
    # Backend tests
    if [ -f "backend/pyproject.toml" ] || [ -f "backend/setup.py" ]; then
        cd backend 2>/dev/null
        python -m pytest --tb=short -q 2>/dev/null && \
            log INFO "Backend tests passed" || \
            log WARN "Backend tests failed or no tests found"
        cd "$PROJECT_ROOT"
    fi
}

#================================================================================
# BACKUP & ROLLBACK
#================================================================================

create_backup() {
    if [ "$CREATE_BACKUP" = false ]; then
        log INFO "Backup skipped (--no-backup)"
        return
    fi
    
    log ACTION "Creating pre-deployment backup..."
    
    local backup_name="pre_deploy_$(date +%Y%m%d_%H%M%S)"
    local backup_path="$BACKUP_DIR/$backup_name"
    
    mkdir -p "$backup_path"
    
    # Backup critical files and directories
    local items_to_backup=(
        ".env"
        ".next"
        "backend/core/"
        "backend/main.py"
        "package.json"
        "package-lock.json"
    )
    
    for item in "${items_to_backup[@]}"; do
        if [ -e "$PROJECT_ROOT/$item" ]; then
            cp -r "$PROJECT_ROOT/$item" "$backup_path/" 2>/dev/null && \
                log INFO "Backed up: $item"
        fi
    done
    
    # Save current git commit
    if git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree &>/dev/null; then
        git -C "$PROJECT_ROOT" rev-parse HEAD > "$backup_path/git_commit.txt" 2>/dev/null
    fi
    
    # Create backup manifest
    cat > "$backup_path/manifest.json" << EOF
{
    "name": "$backup_name",
    "timestamp": "$(date -Iseconds)",
    "version": "$SUPERAI_VERSION",
    "environment": "$DEPLOY_ENV"
}
EOF
    
    log INFO "Backup created: $backup_path"
    
    # Keep only last 5 backups
    ls -dt "$BACKUP_DIR"/pre_deploy_* 2>/dev/null | tail -n +6 | xargs rm -rf 2>/dev/null || true
}

rollback_deployment() {
    log ACTION "Rolling back deployment..."
    
    # Find latest backup
    local latest_backup=$(ls -dt "$BACKUP_DIR"/pre_deploy_* 2>/dev/null | head -1)
    
    if [ -z "$latest_backup" ]; then
        log ERROR "No backup found for rollback"
        exit 1
    fi
    
    confirm "Roll back to backup: $(basename $latest_backup)?"
    
    log INFO "Restoring from: $latest_backup"
    
    # Restore backed up items
    for item in "$latest_backup"/*; do
        local basename=$(basename "$item")
        
        if [ "$basename" != "manifest.json" ] && [ "$basename" != "git_commit.txt" ]; then
            rm -rf "$PROJECT_ROOT/$basename" 2>/dev/null
            cp -r "$item" "$PROJECT_ROOT/" 
            log INFO "Restored: $basename"
        fi
    done
    
    # Restart services
    restart_services
    
    log INFO "Rollback completed! ✓"
}

#================================================================================
# SERVICE MANAGEMENT
#================================================================================

restart_services() {
    log ACTION "Restarting services..."
    
    # Determine how the app is running
    local pm_running=false
    local docker_running=false
    local systemd_running=false
    
    # Check PM2
    if command -v pm2 &>/dev/null && pm2 list 2>/dev/null | grep -q "superai\|supremeai\|next"; then
        pm_running=true
        pm2 restart all
        log INFO "PM2 services restarted"
    fi
    
    # Check Docker Compose
    if [ -f "$PROJECT_ROOT/docker-compose.yml" ]; then
        docker_running=true
        docker compose down && docker compose up -d
        log INFO "Docker containers restarted"
    fi
    
    # Check systemd
    if systemctl is-active --quiet superai 2>/dev/null || \
       systemctl is-active --quiet supremeai 2>/dev/null; then
        systemd_running=true
        sudo systemctl restart superai 2>/dev/null || sudo systemctl restart supremeai
        log INFO "Systemd service restarted"
    fi
    
    # If nothing detected, try common approaches
    if [ "$pm_running" = false ] && [ "$docker_running" = false ] && [ "$systemd_running" = false ]; then
        log WARN "No service manager detected. Manual restart may be needed."
        log INFO "To start manually:"
        log INFO "  Backend: cd backend && uvicorn main:app --host 0.0.0.0 --port 8000"
        log INFO "  Frontend: npm run dev (or serve .next for production)"
    fi
}

#================================================================================
# HEALTH CHECK
#================================================================================

verify_deployment() {
    log ACTION "Verifying deployment..."
    
    sleep 5  # Wait for services to start
    
    local healthy=true
    
    # Check backend
    local backend_url="http://localhost:8000"
    if curl -sf "$backend_url/health" > /dev/null 2>&1; then
        log INFO "✓ Backend health check passed"
    elif curl -sf "$backend_url/docs" > /dev/null 2>&1; then
        log INFO "✓ Backend responding (docs endpoint)"
    else
        log WARN "⚠ Backend may not be running or health endpoint differs"
        healthy=false
    fi
    
    # Check frontend
    local frontend_url="http://localhost:3000"
    if curl -sf "$frontend_url" > /dev/null 2>&1; then
        log INFO "✓ Frontend responding"
    else
        log WARN "⚠ Frontend may not be running on port 3000"
        # Don't fail on this - might be on different port
    fi
    
    # Run comprehensive health check if available
    if [ -f "$SCRIPT_DIR/superai_health_check.py" ]; then
        log INFO "Running comprehensive health check..."
        python3 "$SCRIPT_DIR/superai_health_check.py --quick" 2>/dev/null || true
    fi
    
    if [ "$healthy" = true ]; then
        log INFO "Deployment verified successfully! 🎉"
    else
        log WARN "Deployment completed with warnings. Review logs above."
    fi
}

#================================================================================
# STATUS COMMAND
#================================================================================

show_status() {
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║     🤖 SuperAI Deployment Status        ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    
    echo "📁 Project: $PROJECT_ROOT"
    echo "📅 Version: $SUPERAI_VERSION"
    echo "🕐 Time: $(date)"
    echo ""
    
    echo "--- System Resources ---"
    echo "CPU: $(top -bn1 | grep 'Cpu(s)' | awk '{print $2}' || echo 'N/A')%"
    echo "Memory: $(free -h | awk '/Mem:/{print $3"/"$2}')"
    echo "Disk: $(df -h $PROJECT_ROOT | tail -1 | awk '{print $3"/"$2" ("$5")"}')"
    echo ""
    
    echo "--- Services ---"
    
    # PM2
    if command -v pm2 &>/dev/null; then
        echo "PM2:"
        pm2 list 2>/dev/null | head -10 || echo "  Not running"
    fi
    
    # Docker
    if command -v docker &>/dev/null; then
        echo "Docker:"
        docker ps --format "  {{.Names}}: {{.Status}}" 2>/dev/null | head -5 || echo "  Not running"
    fi
    
    # Ports
    echo ""
    echo "--- Port Status ---"
    for port in 3000 8000 8080; do
        if lsof -i :$port >/dev/null 2>&1 || ss -tlnp | grep -q ":$port "; then
            echo "  Port $port: ✓ In use"
        else
            echo "  Port $port: ✗ Available"
        fi
    done
    
    echo ""
    echo "--- Backups ---"
    local backup_count=$(ls -d "$BACKUP_DIR"/pre_deploy_* 2>/dev/null | wc -l)
    echo "Available backups: $backup_count"
    
    if [ $backup_count -gt 0 ]; then
        echo "Latest: $(ls -dt "$BACKUP_DIR"/pre_deploy_* 2>/dev/null | head -1 | xargs basename)"
    fi
    
    echo ""
}

#================================================================================
# MAIN DEPLOYMENT FLOW
#================================================================================

full_deploy() {
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║   🚀 SuperAI Quick Deploy v$SUPERAI_VERSION      ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    
    log INFO "Starting deployment to $DEPLOY_ENV environment..."
    log INFO "Project root: $PROJECT_ROOT"
    echo ""
    
    # Confirm deployment
    confirm "Proceed with deployment?" || {
        log INFO "Deployment cancelled."
        exit 0
    }
    
    # Create directories
    create_dirs
    
    # Step 1: Pre-flight checks
    preflight_checks
    
    # Step 2: Create backup
    create_backup
    
    # Step 3: Install dependencies
    setup_dependencies
    
    # Step 4: Apply SuperAI patches
    apply_superai_patches
    
    # Step 5: Run tests
    run_tests
    
    # Step 6: Build
    build_frontend
    build_backend
    
    # Step 7: Restart services
    restart_services
    
    # Step 8: Verify
    verify_deployment
    
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║   ✅ Deployment Complete!                 ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    log INFO "Deployed at: $(date '+%Y-%m-%d %H:%M:%S')"
    log INFO "Log file: $DEPLOY_LOG"
    echo ""
    
    # Show next steps
    echo "📋 Next Steps:"
    echo "   1. Test your application at http://localhost:3000"
    echo "   2. Check API docs at http://localhost:8000/docs"
    echo "   3. Monitor with: python3 $SCRIPT_DIR/superai_cpu_monitor.py"
    echo "   4. Run health check: python3 $SCRIPT_DIR/superai_health_check.py"
    echo ""
}

#================================================================================
# ARGUMENT PARSING
#================================================================================

usage() {
    cat << EOF
SuperAI Quick Deploy - One-click deployment for SuperAI platform

Usage: $0 [OPTIONS] [COMMAND]

Commands:
  (no command)    Full deployment workflow
  setup           Initial setup and dependency installation only
  patches         Apply SuperAI optimization patches only
  build           Build frontend and backend only
  deploy          Restart services and verify (assumes already built)
  rollback        Rollback to previous deployment
  status          Show deployment and system status
  backup          Create a backup only

Options:
  -e, --env ENV       Deployment environment (default: production)
  --skip-tests        Skip running tests
  --skip-build        Skip build step (use existing .next)
  --no-patches        Skip applying SuperAI patches
  --no-backup         Skip creating backup before deploy
  -f, --force         Skip confirmation prompts
  -h, --help          Show this help message

Examples:
  $0                          # Full deployment with all checks
  $0 --skip-build --deploy    # Restart services without rebuilding
  $0 --no-patches             # Deploy without applying patches
  $0 rollback                 # Rollback to previous version
  $0 status                  # Show system status

CPU Impact Note:
  Build step uses high CPU for 2-5 minutes (Next.js compilation)
  All other steps use minimal CPU (<5%)
  Total deployment time: 5-15 minutes depending on hardware
EOF
}

# Parse arguments
COMMAND=""
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        setup|patches|build|deploy|rollback|status|backup)
            COMMAND="$1"
            shift
            ;;
        -e|--env)
            DEPLOY_ENV="$2"
            shift 2
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --no-patches)
            APPLY_PATCHES=false
            shift
            ;;
        --no-backup)
            CREATE_BACKUP=false
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log ERROR "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

#================================================================================
# EXECUTION
#================================================================================

# Initialize log
echo "# Deployment Log - Started $(date)" > "$DEPLOY_LOG"

# Execute command
case $COMMAND in
    "")
        full_deploy
        ;;
    setup)
        create_dirs
        preflight_checks
        setup_dependencies
        log INFO "Setup complete! Run '$0' for full deployment."
        ;;
    patches)
        create_dirs
        apply_superai_patches
        ;;
    build)
        create_dirs
        setup_dependencies
        run_tests
        build_frontend
        build_backend
        log INFO "Build complete! Run '$0 deploy' to restart services."
        ;;
    deploy)
        restart_services
        verify_deployment
        ;;
    rollback)
        rollback_deployment
        ;;
    status)
        show_status
        ;;
    backup)
        create_dirs
        create_backup
        ;;
    *)
        usage
        exit 1
        ;;
esac
