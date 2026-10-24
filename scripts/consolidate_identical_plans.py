import os

plans_base = r'f:\supremeai\docs\plans'
archive_base = r'f:\supremeai\docs\archive\plans'

identical_redundant_removals = [
    os.path.join(plans_base, 'features', 'mcp_gateway_dynamic_hub_plan.md'),
    os.path.join(plans_base, 'MISSING_SERVICES_INTEGRATION_PLAN_V4.1.md'),
    os.path.join(plans_base, 'FREE_TIER_UPGRADE_PLAN.md'),
    os.path.join(plans_base, 'PRODUCTION_UPGRADE_PLAN.md'),
    os.path.join(plans_base, 'FREE_TIER_FEDERATION_MASTER_PLAN_V4.md'),
    os.path.join(plans_base, 'FREE_TIER_FEDERATION_PLAN_V3.md'),
    os.path.join(plans_base, 'SUPREMEAI_FREE_TIER_MULTI_SERVICE_SCALE_MASTER_PLAN.md'),
    os.path.join(plans_base, 'UNIVERSAL_ZERO_COMPLEXITY_INTERFACE_PLAN.md'),
    os.path.join(plans_base, 'summary', 'SupremeAI_Deliverables_Summary.md'),
    os.path.join(plans_base, 'summary', 'SupremeAI_Quick_Start_Checklist.md'),
    os.path.join(plans_base, 'summary', 'SupremeAI_Repository_Analysis_Action_Plan.md'),
    os.path.join(plans_base, 'summary', 'SupremeAI_Self_Learning_Current_Status.md'),
    os.path.join(plans_base, 'summary', 'SupremeAI_Ultimate_Controller_Plan.md'),
    os.path.join(plans_base, 'summary', 'SupremeAI_Final_5Model_Structure.md'),
    os.path.join(plans_base, 'summary', 'SupremeAI_Simulator_Controller_Plan.md'),
    os.path.join(plans_base, 'summary', 'SupremeAI_কাজের_পরিকল্পনা_বাংলা.md'),
    os.path.join(plans_base, 'summary', 'SupremeAI_প্রকল্প_সম্পূর্ণ_পরিচিতি_বাংলা.md'),
    os.path.join(plans_base, 'summary', 'UX_Best_Practices_SupremeAI.md'),
]

archive_redirect_stubs = [
    (os.path.join(plans_base, 'SupremeAI_Final_5Model_Structure.md'), os.path.join(archive_base, 'redirect_stubs', 'SupremeAI_Final_5Model_Structure.md')),
    (os.path.join(plans_base, 'SupremeAI_Ultimate_Controller_Plan.md'), os.path.join(archive_base, 'redirect_stubs', 'SupremeAI_Ultimate_Controller_Plan.md')),
    (os.path.join(plans_base, 'summary', 'SupremeAI_Final_5Model_Structure.md'), os.path.join(archive_base, 'redirect_stubs', 'summary_SupremeAI_Final_5Model_Structure.md')),
    (os.path.join(plans_base, 'summary', 'SupremeAI_Ultimate_Controller_Plan.md'), os.path.join(archive_base, 'redirect_stubs', 'summary_SupremeAI_Ultimate_Controller_Plan.md')),
    (os.path.join(plans_base, 'FREE_TIER_FEDERATION_MASTER_PLAN_V4.md'), os.path.join(archive_base, 'redirect_stubs', 'FREE_TIER_FEDERATION_MASTER_PLAN_V4.md')),
    (os.path.join(plans_base, 'MISSING_SERVICES_INTEGRATION_PLAN_V4.1.md'), os.path.join(archive_base, 'redirect_stubs', 'MISSING_SERVICES_INTEGRATION_PLAN_V4.1.md')),
    (os.path.join(plans_base, 'UNIVERSAL_ZERO_COMPLEXITY_INTERFACE_PLAN.md'), os.path.join(archive_base, 'redirect_stubs', 'UNIVERSAL_ZERO_COMPLEXITY_INTERFACE_PLAN.md')),
]

removed = 0
archived = 0
for p in identical_redundant_removals:
    if os.path.exists(p):
        os.remove(p)
        removed += 1

for src, dst in archive_redirect_stubs:
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(src, dst)
        archived += 1

summary_dir = os.path.join(plans_base, 'summary')
if os.path.exists(summary_dir) and len(os.listdir(summary_dir)) == 0:
    os.rmdir(summary_dir)

print(f'Done. Removed {removed} redundant files, archived {archived} redirect stubs.')
