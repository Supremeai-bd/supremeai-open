import os

plans_base = r'f:\supremeai\docs\plans'

renames = {
    # Architecture
    ('architecture', 'REGISTRY CONTROL IN PIPELINE AND DASHBOARD.md'):
        ('architecture', 'registry_control_in_pipeline_and_dashboard.md'),
    ('architecture', 'crown_jewel_implementation_plan.md'):
        ('architecture', 'crown_jewel_real_wiring_analysis.md'),
    ('architecture', 'আউট-অফ-দ্য-বক্স (Out-of-the-Box) রেভোলিউশনারি ব্লুপ্রিন্ট.md'):
        ('architecture', 'out_of_the_box_revolutionary_blueprint_bn.md'),
    ('architecture', 'ইমপ্লিমেন্টেশন প্ল্যান ডাইনামিক কনট্রোল প্লেন (Zero-Hardcoded Runtime Configuration).md'):
        ('architecture', 'dynamic_control_plane_zero_hardcode_plan_bn.md'),

    # Features
    ('features', 'Self-Tracing & Bounded Black-Box Architecture Implementation Plan.md'):
        ('features', 'self_tracing_and_bounded_black_box_architecture.md'),
    ('features', 'Public_mcp_server_implementation_plan.md'):
        ('features', 'personal_public_mcp_server_plan.md'),
    ('features', 'auto_checking_implementation_plan.md'):
        ('features', 'qa_engine_auto_checking_implementation_plan.md'),
    ('features', 'implementation_plan.md'):
        ('features', 'universal_zero_complexity_interface_plan.md'),
    ('features', 'implementation_plan2.md'):
        ('features', 'evolution_patch_implementation_plan.md'),
    ('features', 'implementation_plan22.md'):
        ('features', 'full_integration_master_blueprint_bn.md'),
    ('features', 'implementation_plan_4pilarevulution.md'):
        ('features', 'burj_khalifa_4pillar_evolution_roadmap.md'),
    ('features', 'implementation_plan_for_checking core_philoshopy.md'):
        ('features', 'constitution_ci_audit_system_implementation_plan_bn.md'),
    ('features', 'implementation_plan_for_remaining_task.md'):
        ('features', 'production_readiness_final_stretch_plan_bn.md'),
    ('features', 'implementation_plan_from_old_plan.md'):
        ('features', 'best_practices_unified_implementation_plan.md'),
    ('features', 'implementation_plan_gap_solution.md'):
        ('features', 'codebase_gap_solution_unification_plan_bn.md'),
    ('features', 'kaggle_implementation_plan.md'):
        ('features', 'kaggle_6node_cluster_compute_plan.md'),
    ('features', 'kilo_implementation_plan.md'):
        ('features', 'kilo_ai_integration_backend_refactoring_plan.md'),
    ('features', 'mcp_gateway_implementation_plan.md'):
        ('features', 'personal_mcp_gateway_multitenant_hub_plan.md'),
    ('features', 'mega_free_implementation_plan.md'):
        ('features', 'cloudflare_7node_global_edge_mesh_plan.md'),
    ('features', 'multi model implementation_plan.md'):
        ('features', 'vscode_lm_multi_model_ide_support_plan.md'),
    ('features', 'need_&_supply_implementation_plan.md'):
        ('features', 'self_assembling_need_supply_intelligence_plan.md'),
    ('features', 'openworked_implementation_plan.md'):
        ('features', 'agentic_future_openworked_enhancement_plan.md'),
    ('features', 'plugin becomes an agent capability complete lifecycle.md'):
        ('features', 'plugin_to_agent_capability_lifecycle.md'),
    ('features', 'ultimate_implementation_plan.md'):
        ('features', 'living_autonomous_intelligence_master_plan.md'),

    # Design
    ('design', 'SupremeAI সম্পূর্ণ Frontend পরিকল্পনা.md'):
        ('design', 'complete_frontend_master_plan_bn.md'),
}

count = 0
for (src_folder, src_name), (dst_folder, dst_name) in renames.items():
    src_path = os.path.join(plans_base, src_folder, src_name)
    dst_path = os.path.join(plans_base, dst_folder, dst_name)
    if os.path.exists(src_path):
        if os.path.exists(dst_path) and src_path.lower() != dst_path.lower():
            os.remove(dst_path)

        # Windows case-change safe rename:
        if src_path.lower() == dst_path.lower() and src_path != dst_path:
            temp_path = src_path + '.tmp'
            os.rename(src_path, temp_path)
            os.rename(temp_path, dst_path)
        else:
            os.rename(src_path, dst_path)
        count += 1

print(f'Successfully processed renames: {count}')
