import os
import re
import shutil

src = os.getenv("EXTERNAL_PLANS_SRC", "")
plans_base = os.path.join("docs", "plans")
audits_base = os.path.join("docs", "audits")

os.makedirs(os.path.join(plans_base, "architecture"), exist_ok=True)
os.makedirs(os.path.join(plans_base, "features"), exist_ok=True)
os.makedirs(os.path.join(plans_base, "infrastructure"), exist_ok=True)
os.makedirs(os.path.join(plans_base, "design"), exist_ok=True)
os.makedirs(audits_base, exist_ok=True)

files = os.listdir(src)

def is_duplicate(f):
    m = re.match(r'^(.*?)(\s*\(\d+\)|\s+\d+)\.md$', f)
    if m:
        base = m.group(1) + '.md'
        if os.path.exists(os.path.join(src, base)):
            return True, base
    return False, None

plans_arch = [
    'SUPREMAI_DYNAMIC_AI_ARCHITECTURE_V5.md',
    'SUPREMEAI_UNIFIED_MCP_CONTROL_TOWER_MULTI_TENANT_EXPANDABLE_MASTER_PLAN_BN.md',
    'SUPREMEAI_DISTRIBUTED_INFRASTRUCTURE_CENTRALIZED_CONTROL_PLANE_PLAN.md',
    'SUPREMEAI_DYNAMIC_CONFIGURATION_ZERO_HARDCODE_ROADMAP.md',
    'SUPREMEAI_VENDOR_INDEPENDENT_INTEGRATION_IMPLEMENTATION_PLAN.md',
    'SUPREMEAI_ECOSYSTEM_TRANSFORMATION_FINAL_ROADMAP.md',
    'SUPREMEAI_COMPLETE_INTEGRATION_BLUEPRINT.md',
    'SUPREMEAI_COMPONENT_INTEGRATION_MAP.md',
    'SUPREMEAI_CURRENT_CODEBASE_ALIGNED_MASTER_ROADMAP.md',
    'আউট-অফ-দ্য-বক্স (Out-of-the-Box) রেভোলিউশনারি ব্লুপ্রিন্ট.md',
    'ইমপ্লিমেন্টেশন প্ল্যান ডাইনামিক কনট্রোল প্লেন (Zero-Hardcoded Runtime Configuration).md',
    'crown_jewel_wiring_masterplan.md',
    'crown_jewel_implementation_plan.md',
    'wiring_feature.md',
    'circle_in_codebase.md',
    'ARCHITECTURE_MAP.md',
    'ENTERPRISE_ROADMAP.md',
    'ROADMAP_BANGLA.md',
    'MASTER_PLAN_BANGLA.md',
    'MASTER_PLAN_ANALYSIS_BANGLA.md',
    'REGISTRY CONTROL IN PIPELINE AND DASHBOARD.md',
]

plans_features = [
    'SUPREMEAI_AUTONOMOUS_USER_TASK_AND_SELF_EVOLUTION_MASTER_PLAN.md',
    'SUPREMAI_MISSING_SERVICES_INTEGRATION_PLAN.md',
    'SUPREMEAI_N8N_INTEGRATION_MASTER_PLAN.md',
    'SUPREMEAI_SPEC_KIT_FULL_IMPLEMENTATION_PLAN.md',
    'SUPREMEAI_CAREFULLY_SELECTED_OPEN_SOURCE_COMPONENTS_IMPLEMENTATION_PLAN_UPDATED.md',
    'SUPREMEAI_SELF_EVOLUTION_ZERO_COST_IMPLEMENTATION_PLAN.md',
    'Public_mcp_server_implementation_plan.md',
    'Self-Tracing & Bounded Black-Box Architecture Implementation Plan.md',
    'plugin becomes an agent capability complete lifecycle.md',
    'auto_checking_implementation_plan.md',
    'SUPREMEAI_REMAINING_DYNAMIC_CONFIGURATION_IMPLEMENTATION_PLAN.md',
    'SUPREMEAI_REMAINING_OPEN_SOURCE_INTEGRATION_HARDENING_PLAN.md',
    'SUPREMEAI_WARNING_ELIMINATION_IMPLEMENTATION_PLAN.md',
    'mcp_gateway_implementation_plan.md',
    'kaggle_implementation_plan.md',
    'kilo_implementation_plan.md',
    'mega_audit_172_files_plan.md',
    'mega_free_implementation_plan.md',
    'multi model implementation_plan.md',
    'need_&_supply_implementation_plan.md',
    'openworked_implementation_plan.md',
    'plan_analysis.md',
    'PROJECT_REMEDIATION_PLAN_BN.md',
    'ultimate_implementation_plan.md',
    'mcp-server.md',
    'kilo.md',
]

plans_infra = [
    'SUPREMAI_FREE_TIER_FEDERATION_MASTER_PLAN_V4.md',
    'SUPREMAI_FREE_TIER_FEDERATION_PLAN.md',
    'SUPREMAI_FREE_TIER_MEMORY_CRISIS_REMEDIATION_PLAN.md',
    'SUPREMAI_FREE_TIER_MULTI_SERVICE_SCALE_MASTER_PLAN.md',
    'SUPREMAI_FREE_TIER_UPGRADE_PLAN.md',
    'SUPREMEAI_3_RENDER_SERVICES_GHCR_DEPLOYMENT_ROADMAP_BN.md',
    'SUPREMEAI_CI_RENDER_BUILD_RUNTIME_OPTIMIZATION_PLAN_BN.md',
    'SUPREMEAI_RENDER_MEMORY_REMAINING_ROADMAP.md',
    'SUPREMEAI_RENDER_PRODUCTION_ERROR_WARNING_CLEANUP_PLAN.md',
    'SUPREMEAI_PRODUCTION_UPGRADE_PLAN.md',
    'superai_free_tier_survival_guide.md',
    'INFISICAL_SETUP_GUIDE.md',
    'SUPREMEAI_THIRD_PARTY_ENV_SECRET_CHECKLIST.md',
    'docker.md',
    'render.md',
    'supabase_database_manage.md',
]

plans_design = [
    'SUPREMEAI_2_UI_UX_MASTER_PLAN.md',
    'SUPREMEAI_SINGLE_FRONTEND_ROLE_BASED_ROADMAP.md',
    'SupremeAI সম্পূর্ণ Frontend পরিকল্পনা.md',
    'SUPREMEAI_2_AUTONOMOUS_UI_AGENT_PROMPT.md',
    'SUPREMEAI_ADMIN_DASHBOARD_GAP_ANALYSIS.md',
    'dashboard_design_mockups.md',
]

stats = {'arch': 0, 'features': 0, 'infra': 0, 'design': 0, 'audits': 0, 'skipped_dup': 0}

for f in files:
    is_dup, base_f = is_duplicate(f)
    if is_dup:
        stats['skipped_dup'] += 1
        continue

    src_file = os.path.join(src, f)
    if not os.path.isfile(src_file):
        continue

    fl = f.lower()
    if f in plans_arch or any(p.lower() == fl for p in plans_arch):
        dest = os.path.join(plans_base, 'architecture', f)
        shutil.copy2(src_file, dest)
        stats['arch'] += 1
    elif f in plans_features or any(p.lower() == fl for p in plans_features):
        dest = os.path.join(plans_base, 'features', f)
        shutil.copy2(src_file, dest)
        stats['features'] += 1
    elif f in plans_infra or any(p.lower() == fl for p in plans_infra):
        dest = os.path.join(plans_base, 'infrastructure', f)
        shutil.copy2(src_file, dest)
        stats['infra'] += 1
    elif f in plans_design or any(p.lower() == fl for p in plans_design):
        dest = os.path.join(plans_base, 'design', f)
        shutil.copy2(src_file, dest)
        stats['design'] += 1
    elif 'plan' in fl or 'roadmap' in fl or 'blueprint' in fl:
        dest = os.path.join(plans_base, 'features', f)
        shutil.copy2(src_file, dest)
        stats['features'] += 1
    else:
        dest = os.path.join(audits_base, f)
        shutil.copy2(src_file, dest)
        stats['audits'] += 1

print("Completed copying:")
for k, v in stats.items():
    print(f"  {k}: {v}")
