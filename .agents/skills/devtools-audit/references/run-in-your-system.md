# Running the audit inside your own system

The audit needs network access to the target, so run it where that exists.

## Local machine or any server with Node 20+ and Python 3
```bash
mkdir devtools-audit && cd devtools-audit   # copy scripts/ here
npm i playwright axe-core && npx playwright install --with-deps chromium
node scripts/audit.mjs https://customer.example --out audit.raw.json --device mobile --throttle slow4g
python3 scripts/build_report.py audit.raw.json --out-dir audit-out --label "Customer X"
```
Upload `audit.raw.json` to Claude to continue the delivery steps, or send `audit-out/telegram.txt` yourself.

Login-protected app:
```bash
AUDIT_USER='...' AUDIT_PASS='...' node scripts/audit.mjs https://app.example/dashboard --login-url https://app.example/login --out audit.raw.json
```
Never commit credentials; use CI secrets.

## GitHub Actions (scheduled, starter)
Put the two scripts in `tools/devtools-audit/` of your own repo and add a workflow like this (workflow files live under `.github/`, so add it directly rather than through the Tower bridge, which sends `.github/` changes to admin review):
```yaml
name: frontend-audit
on:
  schedule: [{cron: '0 3 * * *'}]
  workflow_dispatch: {inputs: {url: {required: true}}}
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: {node-version: 24}
      - run: npm i playwright axe-core && npx playwright install --with-deps chromium
        working-directory: tools/devtools-audit
      - run: |
          node scripts/audit.mjs "${{ inputs.url || vars.AUDIT_URL }}" --out audit.raw.json --device mobile --throttle slow4g
          python3 scripts/build_report.py audit.raw.json --out-dir audit-out
        working-directory: tools/devtools-audit
      - uses: actions/upload-artifact@v4
        with: {name: audit-out, path: tools/devtools-audit/audit-out}
      - name: Telegram
        env: {T: '${{ secrets.TELEGRAM_BOT_TOKEN }}', C: '${{ secrets.TELEGRAM_CHAT_ID }}'}
        run: curl -s "https://api.telegram.org/bot$T/sendMessage" --data-urlencode "chat_id=$C" --data-urlencode "text@tools/devtools-audit/audit-out/telegram.txt" >/dev/null
```
The Tower submission step needs Tower credentials; until those are available to CI, upload the artifact and let Claude submit `tower_payload.json` from a chat session.

## Lighthouse (optional extra)
`npx lighthouse https://customer.example --output=json --output-path=lh.json --chrome-flags="--headless"` then pass `--lighthouse lh.json` to `build_report.py` to add category scores and the top failed audits.
