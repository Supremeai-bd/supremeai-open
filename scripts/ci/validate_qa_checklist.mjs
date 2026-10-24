import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { parse } from 'yaml';

const root = process.cwd();
const checklistDir = join(root, 'qa', 'checklist');
const allowedSeverities = new Set(['P0', 'P1', 'P2', 'P3']);
const allowedRoles = new Set(['guest', 'customer', 'admin', 'service', 'operator', 'reviewer', 'security']);
const required = ['id', 'area', 'role', 'name', 'severity', 'automated'];
const allowedAutomationKeys = new Set(['frontend-build', 'frontend-typecheck', 'frontend-unit-tests', 'backend-health-deploy', 'frontend-api-origin', 'security-preflight', 'tenant-isolation', 'rollback-restore', 'ai-quality-review', 'accessibility-review', 'mcp-deployed-transport', 'privacy-retention']);

if (!existsSync(checklistDir)) {
  console.error(`Missing checklist directory: ${checklistDir}`);
  process.exit(1);
}

const files = readdirSync(checklistDir).filter((file) => file.endsWith('.yaml')).sort();
if (files.length === 0) {
  console.error('No QA checklist files found.');
  process.exit(1);
}

const ids = new Set();
const errors = [];
let itemCount = 0;
let automatedCount = 0;

for (const file of files) {
  const path = join(checklistDir, file);
  let items;
  try {
    items = parse(readFileSync(path, 'utf8'));
  } catch (error) {
    errors.push(`${file}: invalid YAML (${error.message})`);
    continue;
  }

  if (!Array.isArray(items)) {
    errors.push(`${file}: top-level value must be an array`);
    continue;
  }

  items.forEach((item, index) => {
    const location = `${file}[${index}]`;
    itemCount += 1;
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      errors.push(`${location}: item must be an object`);
      return;
    }

    for (const field of required) {
      if (!(field in item)) errors.push(`${location}: missing ${field}`);
    }
    if (typeof item.id !== 'string' || !/^[A-Z]+-[0-9]+$/.test(item.id)) {
      errors.push(`${location}: id must match AREA-123`);
    } else if (ids.has(item.id)) {
      errors.push(`${location}: duplicate id ${item.id}`);
    } else {
      ids.add(item.id);
    }
    if (typeof item.area !== 'string' || item.area.trim() === '') errors.push(`${location}: area must be non-empty`);
    if (!allowedRoles.has(item.role)) errors.push(`${location}: unsupported role ${item.role}`);
    if (typeof item.name !== 'string' || item.name.trim() === '') errors.push(`${location}: name must be non-empty`);
    if (!allowedSeverities.has(item.severity)) errors.push(`${location}: unsupported severity ${item.severity}`);
    if (typeof item.automated !== 'boolean') errors.push(`${location}: automated must be boolean`);
    // Two checklist schema generations coexist (Task 7-e):
    //  - contract items (core.yaml): automated checks carry a `check` command and
    //    must declare a whitelisted `automation_key`.
    //  - browser items (guest/customer/admin/security, QA-engine Part-1 schema):
    //    they carry `action`/`assert` step lists and are covered by
    //    qa/scripts/validate-checklist.ts instead — the automation_key rule does
    //    not apply to them.
    const isNewSchema = Array.isArray(item.action) && Array.isArray(item.assert);
    if (item.automated) {
      automatedCount += 1;
      if (!isNewSchema && (typeof item.automation_key !== 'string' || !allowedAutomationKeys.has(item.automation_key))) {
        errors.push(`${location}: automated checks require a supported automation_key`);
      }
    }
    if (!item.automated && (typeof item.manual_note !== 'string' || item.manual_note.trim() === '')) {
      errors.push(`${location}: manual_note is required for manual checks`);
    }
  });
}

if (errors.length) {
  console.error(errors.map((error) => `- ${error}`).join('\n'));
  process.exit(1);
}

console.log(`QA checklist valid: ${files.length} files, ${itemCount} items, ${automatedCount} automated, ${itemCount - automatedCount} manual.`);
