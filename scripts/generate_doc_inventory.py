#!/usr/bin/env python3
"""Generate docs/DOCUMENTATION_MASTER_INDEX.md listing all documentation files in SupremeAI with summaries."""

import os
import re

ignore_dirs = {
    '.venv',
    'node_modules',
    '.git',
    '.pytest_cache',
    '__pycache__',
    'dist',
    'build',
    '.next',
}

md_files = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ignore_dirs]
    for file in files:
        if file.endswith('.md'):
            rel_path = os.path.relpath(os.path.join(root, file), '.').replace('\\', '/')
            md_files.append(rel_path)

md_files.sort()


def extract_summary(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        lines = [l.strip() for l in content.splitlines() if l.strip()]
        title = ''
        summary = ''

        # Check YAML frontmatter summary/description
        summary_match = re.search(r'description:\s*["\']?(.*?)["\']?\n', content)
        if summary_match and summary_match.group(1):
            summary = summary_match.group(1).strip()

        for line in lines[:25]:
            if line.startswith('#') and not title:
                title = re.sub(r'^[#\s]+', '', line).strip()
            elif (
                not summary
                and not line.startswith('#')
                and not line.startswith('---')
                and not line.startswith('>')
                and not line.startswith('|')
                and not line.startswith('-')
                and not line.startswith('*')
                and not line.startswith('`')
                and len(line) > 15
            ):
                summary = line

        if len(summary) > 160:
            summary = summary[:157] + '...'

        if not title:
            title = os.path.basename(filepath)
        if not summary:
            summary = 'System documentation and operational guidance file.'

        title = title.replace('|', '\\|').replace('\n', ' ')
        summary = summary.replace('|', '\\|').replace('\n', ' ')

        return title, summary
    except Exception as e:
        return os.path.basename(filepath), f'Operational document file: {str(e)}'


categorized = {}
for path in md_files:
    parts = path.split('/')
    if len(parts) == 1:
        cat = 'Root Documents'
    else:
        cat = parts[0]
        if cat == 'docs':
            if len(parts) > 2:
                cat = f'docs/{parts[1]}'
            else:
                cat = 'docs (Root)'

    if cat not in categorized:
        categorized[cat] = []

    title, summary = extract_summary(path)
    categorized[cat].append((path, title, summary))

out_path = 'docs/DOCUMENTATION_MASTER_INDEX.md'
os.makedirs(os.path.dirname(out_path), exist_ok=True)

with open(out_path, 'w', encoding='utf-8') as f:
    f.write('# SupremeAI — Master Documentation Inventory & Index\n\n')
    f.write(
        'This document provides a comprehensive, centralized index of all documentation, specification, '
        'and operational markdown (`.md`) files in the SupremeAI repository.\n\n'
    )
    f.write(f'**Total Document Files Tracked:** `{len(md_files)}`  \n')
    f.write('**Generated Date:** `2026-09-12`  \n\n')
    f.write('---\n\n')
    f.write('## Table of Contents & Category Summary\n\n')
    f.write('| Category / Section | File Count |\n| :--- | :--- |\n')

    for cat, items in sorted(categorized.items()):
        anchor = (
            cat.lower()
            .replace(' ', '-')
            .replace('/', '')
            .replace('(', '')
            .replace(')', '')
        )
        f.write(f'| [{cat}](#{anchor}) | {len(items)} |\n')

    f.write('\n---\n\n')

    global_idx = 1
    for cat, items in sorted(categorized.items()):
        f.write(f'## {cat}\n\n')
        f.write('| # | File Path / Name | Title / Header | Purpose & Summary |\n')
        f.write('| :--- | :--- | :--- | :--- |\n')

        for path, title, summary in items:
            f.write(
                f'| {global_idx} | [`{path}`](file:///f:/supremeai/{path}) | **{title}** | {summary} |\n'
            )
            global_idx += 1

        f.write('\n')

print(f'Successfully generated {out_path} with {len(md_files)} entries across {len(categorized)} categories.')
