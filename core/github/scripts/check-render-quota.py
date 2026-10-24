import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RENDER_FREE_MINUTES = 500          # Render free tier monthly limit
THRESHOLD_PERCENT   = 95           # Activate GHA build if usage >= 95%
CACHE_FILE          = "render_minutes_cache.json"

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def get_billing_cycle_start(deploys: list, env_var_name: str, default_day: int) -> str:
    """
    বাংলা মন্তব্য:
    Render billing cycle reset day হিসাব করে।
    ১. প্রথমে environment variable (যেমন RENDER_BILLING_DAY) চেক করে।
    ২. না থাকলে deploys list-এর সবচেয়ে পুরনো deploy-এর দিন ব্যবহার করে (auto-detection)।
    ৩. কোনোটিই না থাকলে default_day ব্যবহার করে।
    """
    billing_day = None
    env_val = os.environ.get(env_var_name, "")
    if env_val.isdigit():
        billing_day = int(env_val)

    if billing_day is None and deploys:
        # Auto-detect billing day from oldest deploy
        dates = []
        for item in deploys:
            d = item.get("deploy", item)
            created = d.get("createdAt", "")
            if created:
                dates.append(created)
        if dates:
            oldest_str = min(dates)
            try:
                dt = datetime.fromisoformat(oldest_str.replace("Z", "+00:00"))
                billing_day = dt.day
                print(f"[AUTO] Auto-detected billing day from oldest deploy: {billing_day} (from {oldest_str[:10]})")
            except Exception as exc:
                print(f"[WARN] Could not parse deploy date '{oldest_str}': {exc}", file=sys.stderr)
    if billing_day is None:
        billing_day = default_day
        print(f"[INFO] Using default billing day: {billing_day}")

    n = now_utc()
    if n.day >= billing_day:
        try:
            start = n.replace(day=billing_day, hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            import calendar
            last_day = calendar.monthrange(n.year, n.month)[1]
            start = n.replace(day=last_day, hour=0, minute=0, second=0, microsecond=0)
    else:
        prev_month = n.month - 1 if n.month > 1 else 12
        prev_year  = n.year if n.month > 1 else n.year - 1
        try:
            start = n.replace(year=prev_year, month=prev_month, day=billing_day,
                              hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            import calendar
            last_day = calendar.monthrange(prev_year, prev_month)[1]
            start = n.replace(year=prev_year, month=prev_month, day=last_day,
                              hour=0, minute=0, second=0, microsecond=0)

    return start.isoformat().replace("+00:00", "Z"), billing_day

def format_local_dt(iso_str: str) -> str:
    try:
        dt = datetime.strptime(iso_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso_str

def fetch_deploys(api_key: str, service_id: str) -> list[dict]:
    url = f"https://api.render.com/v1/services/{service_id}/deploys?limit=100"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[WARN] Render API fetch failed: {e}", file=sys.stderr)
        return []

def calc_usage(deploys: list[dict], month_start: str) -> dict:
    total_minutes = 0.0
    daily_breakdown = {}
    deploy_log = []

    for item in deploys:
        deploy = item.get("deploy", item)
        created  = deploy.get("createdAt", "")
        finished = deploy.get("finishedAt", "")
        status   = deploy.get("status", "")
        deploy_id = deploy.get("id", "unknown")

        if not created or not finished:
            continue
        if created < month_start:
            continue
        if status not in ("live", "failed", "deactivated"):
            continue

        try:
            # Parse using fromisoformat which handles varying microsecond lengths and presence/absence of microseconds
            t1 = datetime.fromisoformat(created.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            duration_min = (t2 - t1).total_seconds() / 60

            day_key = t1.strftime("%Y-%m-%d")
            daily_breakdown[day_key] = daily_breakdown.get(day_key, 0.0) + duration_min
            total_minutes += duration_min

            deploy_log.append({
                "id": deploy_id,
                "date": day_key,
                "started_at": format_local_dt(created),
                "finished_at": format_local_dt(finished),
                "duration_min": round(duration_min, 2),
                "status": status,
            })
        except Exception as e:
            print(f"[WARN] Parse error for deploy {deploy_id}: {e}", file=sys.stderr)

    deploy_log.sort(key=lambda x: x["started_at"], reverse=True)
    return {
        "total_minutes": round(total_minutes, 2),
        "daily_breakdown": daily_breakdown,
        "deploy_log": deploy_log,
    }

def load_cache() -> dict:
    p = Path(CACHE_FILE)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception as exc:
            print(f"[WARN] Cache file unreadable, ignoring: {exc}", file=sys.stderr)
    return {}

def main():
    # Configure stdout/stderr encodings
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        print('Silenced error in except block')

    # Load .env for local testing if it exists (merge parent and local envs)
    for path in ["../.env", ".env", "../../.env"]:
        if Path(path).exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(path)
            except ImportError:
                print('Silenced error in except block')

    api_key_primary = os.environ.get("RENDER_API_KEY", "")
    api_key_backup  = os.environ.get("RENDER_API_KEY_BACKUP", "")
    primary_svc_id  = os.environ.get("PRIMARY_SVC_ID", "srv-d9d3n58js32c738n79k0")
    backup_svc_id   = os.environ.get("BACKUP_SVC_ID", "srv-da35gg2bkg8c73fp1mu0")

    current_time = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    print(f"[INFO] Checking Render quota at: {current_time}\n")

    # Fetch deploys first to allow auto-detection of billing days
    primary_deploys = []
    backup_deploys = []

    if api_key_primary:
        primary_deploys = fetch_deploys(api_key_primary, primary_svc_id)
    if api_key_backup:
        backup_deploys = fetch_deploys(api_key_backup, backup_svc_id)

    # Detect cycle start dates
    p_start, p_day = get_billing_cycle_start(primary_deploys, "RENDER_BILLING_DAY", 17)
    b_start, b_day = get_billing_cycle_start(backup_deploys, "RENDER_BILLING_DAY_BACKUP", 21)

    print(f"[DATE] Primary billing cycle started: {p_start[:10]} (day {p_day})")
    print(f"[DATE] Backup billing cycle started:  {b_start[:10]} (day {b_day})\n")

    combined_daily = {}
    combined_log = []
    total_minutes = 0.0

    # Calculate for Primary
    if primary_deploys:
        result = calc_usage(primary_deploys, p_start)
        mins = result["total_minutes"]
        total_minutes += mins
        for day, m in result["daily_breakdown"].items():
            combined_daily[day] = round(combined_daily.get(day, 0.0) + m, 2)
        for entry in result["deploy_log"]:
            entry["service"] = "Primary (User)"
        combined_log.extend(result["deploy_log"])
        print(f"[METRIC] Primary (User): {mins:.1f} minutes this cycle")

    # Calculate for Backup
    if backup_deploys:
        result = calc_usage(backup_deploys, b_start)
        mins = result["total_minutes"]
        total_minutes += mins
        for day, m in result["daily_breakdown"].items():
            combined_daily[day] = round(combined_daily.get(day, 0.0) + m, 2)
        for entry in result["deploy_log"]:
            entry["service"] = "Backup (Admin)"
        combined_log.extend(result["deploy_log"])
        print(f"[METRIC] Backup (Admin): {mins:.1f} minutes this cycle")

    # Print daily breakdown
    if combined_daily:
        print("\n[DATE] Combined daily breakdown (recent):")
        for day in sorted(combined_daily.keys(), reverse=True)[:7]:
            bar = "#" * int(combined_daily[day] / 5)
            print(f"   {day}: {combined_daily[day]:6.1f} min  {bar}")

    threshold_minutes = RENDER_FREE_MINUTES * (THRESHOLD_PERCENT / 100)
    use_github_build  = total_minutes >= threshold_minutes
    pct_used = (total_minutes / RENDER_FREE_MINUTES) * 100
    remaining = max(0.0, RENDER_FREE_MINUTES - total_minutes)

    print(f"\n[REPORT] Total: {total_minutes:.1f} / {RENDER_FREE_MINUTES} min ({pct_used:.1f}%)")
    print(f"[REPORT] Remaining: {remaining:.1f} min")
    print(f"[REPORT] Threshold: {threshold_minutes:.0f} min ({THRESHOLD_PERCENT}%)")
    print(f"[REPORT] GitHub build mode: {'ACTIVE' if use_github_build else 'inactive'}")

    if pct_used > 80.0:
        print("🚨 [WARNING] Render Free Tier Build Quota approaching depletion (>80% used)!")

    # Save cache
    combined_log.sort(key=lambda x: x["started_at"], reverse=True)
    cache_data = {
        "last_checked_at": now_utc().isoformat().replace("+00:00", "Z"),
        "last_checked_date": now_utc().strftime("%Y-%m-%d"),
        "primary_billing_start": p_start[:10],
        "backup_billing_start": b_start[:10],
        "primary_billing_day": p_day,
        "backup_billing_day": b_day,
        "total_minutes": round(total_minutes, 2),
        "remaining_minutes": round(remaining, 2),
        "pct_used": round(pct_used, 2),
        "threshold_pct": THRESHOLD_PERCENT,
        "use_github_build": use_github_build,
        "daily_breakdown": combined_daily,
        "deploy_log": combined_log[:50],
    }
    Path(CACHE_FILE).write_text(json.dumps(cache_data, indent=2))
    print(f"\n[INFO] Cache saved to {CACHE_FILE}")

    # Set GHA outputs
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"use_github_build={'true' if use_github_build else 'false'}\n")
            f.write(f"minutes_used={total_minutes:.1f}\n")
            f.write(f"pct_used={pct_used:.1f}\n")
            f.write(f"remaining_min={remaining:.1f}\n")
            f.write(f"checked_at={current_time}\n")

    sys.exit(0)

if __name__ == "__main__":
    main()
