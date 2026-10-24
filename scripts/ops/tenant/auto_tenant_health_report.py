import sys

#!/usr/bin/env python
"""
auto_tenant_health_report.py
============================
Generates periodic health reports for all tenants in the SupremeAI 2.0 platform.

This script:
1. Queries all tenants from Firestore
2. Collects usage metrics, performance data, and health indicators
3. Generates a comprehensive report
4. Optionally sends reports to tenants and administrators
5. Identifies tenants that may need attention (over quota, inactive, etc.)

Environment Variables:
- GOOGLE_CLOUD_PROJECT: Google Cloud project ID
- FIRESTORE_DATABASE_ID: Firestore database ID (optional)
- REPORT_RECIPIENTS: Comma-separated list of email addresses to send reports to
- SEND_TENANT_REPORTS: Whether to send individual reports to tenants (default: true)
- ADMIN_ONLY: Whether to only generate admin summary (default: false)
- REPORT_FORMAT: Format for report output (markdown, html, json) (default: markdown)
- SENDGRID_API_KEY: SendGrid API key for email delivery (optional)
"""

import json
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from google.cloud import firestore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE_ID")
REPORT_RECIPIENTS = os.getenv("REPORT_RECIPIENTS", "")
SEND_TENANT_REPORTS = os.getenv("SEND_TENANT_REPORTS", "true").lower() == "true"
ADMIN_ONLY = os.getenv("ADMIN_ONLY", "false").lower() == "true"
REPORT_FORMAT = os.getenv("REPORT_FORMAT", "markdown").lower()
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

def get_firestore_client() -> firestore.Client | None:
    """Get a Firestore client."""
    try:
        if DATABASE_ID:
            return firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
        else:
            return firestore.Client(project=PROJECT_ID)
    except Exception as e:
        logger.error(f"Failed to create Firestore client: {e}")
        return None

def get_all_tenants(db: firestore.Client) -> list[dict[str, Any]]:
    """Retrieve all tenant documents."""
    try:
        tenants = []
        tenants_ref = db.collection('tenants')

        for doc in tenants_ref.stream():
            tenant_data = doc.to_dict()
            tenant_data['tenant_id'] = doc.id
            tenants.append(tenant_data)

        return tenants
    except Exception as e:
        logger.error(f"Failed to retrieve tenants: {e}")
        return []

def get_tenant_usage_stats(db: firestore.Client, tenant_id: str) -> dict[str, Any]:
    """Get usage statistics for a specific tenant."""
    try:
        stats = {
            'api_calls_today': 0,
            'storage_mb': 0,
            'compute_minutes_today': 0,
            'active_users': 0,
            'last_activity': None
        }

        tenant_ref = db.collection('tenants').document(tenant_id)

        # Get usage from current period
        usage_doc = tenant_ref.collection('usage').document('current').get()
        if usage_doc.exists:
            usage_data = usage_doc.to_dict()
            stats.update({
                'api_calls_today': usage_data.get('api_calls', 0),
                'storage_mb': usage_data.get('storage_mb', 0),
                'compute_minutes_today': usage_data.get('compute_minutes', 0),
                'last_activity': usage_data.get('last_updated')
            })

        # Get active users count
        users_col = tenant_ref.collection('users')
        active_users = users_col.where('status', '==', 'active').get()
        stats['active_users'] = len(active_users)

        return stats
    except Exception as e:
        logger.error(f"Failed to get usage stats for tenant {tenant_id}: {e}")
        return {
            'api_calls_today': 0,
            'storage_mb': 0,
            'compute_minutes_today': 0,
            'active_users': 0,
            'last_activity': None,
            'error': str(e)
        }

def get_tenant_limits(db: firestore.Client, tenant_id: str) -> dict[str, Any]:
    """Get quota limits for a specific tenant."""
    try:
        limits_doc = db.collection('tenants').document(tenant_id).collection('limits').document('default').get()
        if limits_doc.exists:
            return limits_doc.to_dict()
        else:
            # Return default limits if not set
            return {
                'api_calls_per_month': 10000,
                'storage_mb': 1000,
                'compute_minutes_per_month': 500,
                'max_users': 5
            }
    except Exception as e:
        logger.error(f"Failed to get limits for tenant {tenant_id}: {e}")
        return {
            'api_calls_per_month': 10000,
            'storage_mb': 1000,
            'compute_minutes_per_month': 500,
            'max_users': 5,
            'error': str(e)
        }

def calculate_usage_percentage(used: float, limit: float) -> float:
    """Calculate usage percentage, handling edge cases."""
    if limit <= 0:
        return 0.0
    return min(100.0, (used / limit) * 100.0)

def assess_tenant_health(usage: dict[str, Any], limits: dict[str, Any]) -> dict[str, Any]:
    """Assess the health status of a tenant based on usage vs limits."""
    health = {
        'status': 'healthy',  # healthy, warning, critical, inactive
        'issues': [],
        'warnings': [],
        'metrics': {}
    }

    # Check API usage
    api_used = usage.get('api_calls_today', 0)
    api_limit = limits.get('api_calls_per_month', 10000)
    # Approximate daily limit (assuming 30-day month)
    api_daily_limit = api_limit / 30
    api_percent = calculate_usage_percentage(api_used, api_daily_limit)
    health['metrics']['api_usage_percent'] = round(api_percent, 1)

    if api_percent >= 90:
        health['status'] = 'critical'
        health['issues'].append(f"API usage at {api_percent:.1f}% of daily limit")
    elif api_percent >= 75:
        if health['status'] == 'healthy':
            health['status'] = 'warning'
        health['warnings'].append(f"API usage at {api_percent:.1f}% of daily limit")

    # Check storage usage
    storage_used = usage.get('storage_mb', 0)
    storage_limit = limits.get('storage_mb', 1000)
    storage_percent = calculate_usage_percentage(storage_used, storage_limit)
    health['metrics']['storage_usage_percent'] = round(storage_percent, 1)

    if storage_percent >= 90:
        if health['status'] == 'healthy':
            health['status'] = 'critical'
        elif health['status'] == 'warning':
            pass  # Keep as critical if already critical
        else:
            health['status'] = 'warning'
        health['issues'].append(f"Storage usage at {storage_percent:.1f}% of limit")
    elif storage_percent >= 75:
        if health['status'] == 'healthy':
            health['status'] = 'warning'
        health['warnings'].append(f"Storage usage at {storage_percent:.1f}% of limit")

    # Check compute usage
    compute_used = usage.get('compute_minutes_today', 0)
    compute_limit = limits.get('compute_minutes_per_month', 500)
    # Approximate daily limit
    compute_daily_limit = compute_limit / 30
    compute_percent = calculate_usage_percentage(compute_used, compute_daily_limit)
    health['metrics']['compute_usage_percent'] = round(compute_percent, 1)

    if compute_percent >= 90:
        if health['status'] == 'healthy':
            health['status'] = 'critical'
        elif health['status'] == 'warning':
            pass  # Keep as critical if already critical
        else:
            health['status'] = 'warning'
        health['issues'].append(f"Compute usage at {compute_percent:.1f}% of daily limit")
    elif compute_percent >= 75:
        if health['status'] == 'healthy':
            health['status'] = 'warning'
        health['warnings'].append(f"Compute usage at {compute_percent:.1f}% of daily limit")

    # Check for inactivity (no activity in last 7 days)
    last_activity = usage.get('last_activity')
    if last_activity:
        try:
            if isinstance(last_activity, str):
                last_active = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
            else:
                # Assume it's a Firestore timestamp
                last_active = last_activity

            days_inactive = (datetime.now(timezone.utc) - last_active).days
            if days_inactive > 7:
                health['issues'].append(f"No activity for {days_inactive} days")
                if health['status'] == 'healthy':
                    health['status'] = 'inactive'
                elif health['status'] == 'warning':
                    pass  # Keep warning if already set
        except Exception as e:
            logger.warning(f"Could not parse last_activity for tenant: {e}")

    return health

def generate_tenant_report(tenant: dict[str, Any], usage: dict[str, Any],
                          limits: dict[str, Any], health: dict[str, Any]) -> str:
    """Generate a health report for a single tenant."""
    tenant_id = tenant.get('tenant_id', 'unknown')
    tenant_name = tenant.get('display_name', tenant.get('email', 'Unknown'))
    template = tenant.get('template', 'unknown')
    status = tenant.get('status', 'unknown')
    created_at = tenant.get('created_at')

    # Format timestamps
    if hasattr(created_at, 'strftime'):
        created_str = created_at.strftime('%Y-%m-%d')
    else:
        created_str = str(created_at) if created_at else 'Unknown'

    if REPORT_FORMAT == 'json':
        report_data = {
            'tenant_id': tenant_id,
            'tenant_name': tenant_name,
            'template': template,
            'status': status,
            'created_at': created_str,
            'usage': usage,
            'limits': limits,
            'health': health,
            'generated_at': datetime.now(timezone.utc).isoformat()
        }
        return json.dumps(report_data, indent=2, default=str)

    elif REPORT_FORMAT == 'html':
        # HTML report generation
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Tenant Health Report: {tenant_name}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #f0f0f0; padding: 15px; border-radius: 5px; }}
                .section {{ margin: 20px 0; }}
                .metric {{ display: inline-block; margin: 10px; padding: 10px; background-color: #f9f9f9; border-radius: 3px; }}
                .status-healthy {{ color: green; }}
                .status-warning {{ color: orange; }}
                .status-critical {{ color: red; }}
                .status-inactive {{ color: gray; }}
                .issue {{ color: red; }}
                .warning {{ color: orange; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Tenant Health Report</h1>
                <p><strong>Tenant ID:</strong> {tenant_id}</p>
                <p><strong>Name:</strong> {tenant_name}</p>
                <p><strong>Template:</strong> {template}</p>
                <p><strong>Status:</strong> <span class="status-{health['status']}">{health['status'].upper()}</span></p>
                <p><strong>Created:</strong> {created_str}</p>
            </div>

            <div class="section">
                <h2>Usage Metrics</h2>
                <div class="metric">API Calls Today: {usage.get('api_calls_today', 0):,}</div>
                <div class="metric">Storage: {usage.get('storage_mb', 0):.1f} MB</div>
                <div class="metric">Compute Minutes Today: {usage.get('compute_minutes_today', 0):,}</div>
                <div class="metric">Active Users: {usage.get('active_users', 0)}</div>
            </div>

            <div class="section">
                <h2>Usage vs Limits</h2>
                <div class="metric">API Usage: {health['metrics'].get('api_usage_percent', 0):.1f}%</div>
                <div class="metric">Storage Usage: {health['metrics'].get('storage_usage_percent', 0):.1f}%</div>
                <div class="metric">Compute Usage: {health['metrics'].get('compute_usage_percent', 0):.1f}%</div>
            </div>

            <div class="section">
                <h2>Health Status</h2>
                <p><strong>Overall Status:</strong> <span class="status-{health['status']}">{health['status'].upper()}</span></p>
        """

        if health['issues']:
            html += "<h3>Issues:</h3><ul class='issue'>"
            for issue in health['issues']:
                html += f"<li>{issue}</li>"
            html += "</ul>"

        if health['warnings']:
            html += "<h3>Warnings:</h3><ul class='warning'>"
            for warning in health['warnings']:
                html += f"<li>{warning}</li>"
            html += "</ul>"

        html += """
            </div>
        </body>
        </html>
        """
        return html

    else:  # Default to markdown
        report = f"""# Tenant Health Report: {tenant_name}

**Tenant ID:** {tenant_id}
**Display Name:** {tenant_name}
**Template:** {template}
**Account Status:** {status}
**Created:** {created_str}
**Report Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

## 📊 Usage Metrics
- **API Calls Today:** {usage.get('api_calls_today', 0):,}
- **Storage Usage:** {usage.get('storage_mb', 0):.1f} MB
- **Compute Minutes Today:** {usage.get('compute_minutes_today', 0):,}
- **Active Users:** {usage.get('active_users', 0)}
- **Last Activity:** {usage.get('last_activity', 'Unknown')}

## 📈 Usage vs Limits
- **API Usage:** {health['metrics'].get('api_usage_percent', 0):.1f}% of daily limit
- **Storage Usage:** {health['metrics'].get('storage_usage_percent', 0):.1f}% of monthly limit
- **Compute Usage:** {health['metrics'].get('compute_usage_percent', 0):.1f}% of daily limit

## 🏥 Health Status
**Overall Status:** {'🟢 Healthy' if health['status'] == 'healthy' else '🟡 Warning' if health['status'] == 'warning' else '🔴 Critical' if health['status'] == 'critical' else '⚪ Inactive'}

"""

        if health['issues']:
            report += "### ❌ Issues Detected\n"
            for issue in health['issues']:
                report += f"- {issue}\n"
            report += "\n"

        if health['warnings']:
            report += "### ⚠️ Warnings\n"
            for warning in health['warnings']:
                report += f"- {warning}\n"
            report += "\n"

        if not health['issues'] and not health['warnings']:
            report += "✅ No issues detected - tenant is operating normally\n\n"

        # Add recommendations based on health status
        if health['status'] in ['warning', 'critical']:
            report += "### 💡 Recommendations\n"
            if health['metrics'].get('api_usage_percent', 0) >= 75:
                report += "- Consider upgrading your plan or optimizing API usage\n"
            if health['metrics'].get('storage_usage_percent', 0) >= 75:
                report += "- Review storage usage and consider archiving old data\n"
            if health['metrics'].get('compute_usage_percent', 0) >= 75:
                report += "- Optimize workflows to reduce compute consumption\n"
            if 'inactive' in health['status'] or any('activity' in issue.lower() for issue in health['issues']):
                report += "- Re-engage with the platform to maintain service quality\n"

    return report

def send_report_via_email(recipient: str, subject: str, body: str, is_html: bool = False) -> bool:
    """Send a report via email."""
    try:
        # Use SendGrid if available
        if SENDGRID_API_KEY:
            try:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail

                message = Mail(
                    from_env='SENDER_EMAIL',
                    to_emails=recipient,
                    subject=subject,
                    html_content=body if is_html else None,
                    plain_text_content=body if not is_html else None
                )

                sg = SendGridAPIClient(SENDGRID_API_KEY)
                response = sg.send(message)
                print(f"📧 Sent report via SendGrid to {recipient} (Status: {response.status_code})")
                return True
            except ImportError:
                print("⚠️  SendGrid not installed - falling back to SMTP")
            except Exception as e:
                print(f"⚠️  SendGrid failed: {e} - falling back to SMTP")

        # Fallback to SMTP
        smtp_server = os.getenv("SMTP_SERVER", "localhost")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
        sender_email = os.getenv("SENDER_EMAIL", "noreply@supremeai.com")

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient
        msg['Subject'] = subject

        # Attach body as appropriate type
        if is_html:
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))

        # Only actually send if not in dry-run mode
        if os.getenv("DRY_RUN", "false").lower() != "true":
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            text = msg.as_string()
            server.sendmail(sender_email, recipient, text)
            server.quit()
            logger.info(f"Report sent to {recipient}")
        else:
            print(f"🔍 [DRY RUN] Would send report to {recipient}")

        return True
    except Exception as e:
        logger.error(f"Failed to send report to {recipient}: {e}")
        return False

def generate_summary_report(all_tenants_data: list[dict[str, Any]]) -> str:
    """Generate a summary report of all tenants."""
    total_tenants = len(all_tenants_data)
    healthy_count = len([t for t in all_tenants_data if t['health']['status'] == 'healthy'])
    warning_count = len([t for t in all_tenants_data if t['health']['status'] == 'warning'])
    critical_count = len([t for t in all_tenants_data if t['health']['status'] == 'critical'])
    inactive_count = len([t for t in all_tenants_data if t['health']['status'] == 'inactive'])

    # Calculate averages
    avg_api_usage = sum(t['health']['metrics'].get('api_usage_percent', 0) for t in all_tenants_data) / max(total_tenants, 1)
    avg_storage_usage = sum(t['health']['metrics'].get('storage_usage_percent', 0) for t in all_tenants_data) / max(total_tenants, 1)
    avg_compute_usage = sum(t['health']['metrics'].get('compute_usage_percent', 0) for t in all_tenants_data) / max(total_tenants, 1)

    # Find top users by various metrics
    top_api_users = sorted(all_tenants_data, key=lambda x: x['usage'].get('api_calls_today', 0), reverse=True)[:5]
    top_storage_users = sorted(all_tenants_data, key=lambda x: x['usage'].get('storage_mb', 0), reverse=True)[:5]

    if REPORT_FORMAT == 'json':
        summary = {
            'report_generated': datetime.now(timezone.utc).isoformat(),
            'total_tenants': total_tenants,
            'health_distribution': {
                'healthy': healthy_count,
                'warning': warning_count,
                'critical': critical_count,
                'inactive': inactive_count
            },
            'average_usage': {
                'api_percent': round(avg_api_usage, 1),
                'storage_percent': round(avg_storage_usage, 1),
                'compute_percent': round(avg_compute_usage, 1)
            },
            'top_users': {
                'by_api_calls': [{'tenant_id': t['tenant_id'], 'name': t['tenant_name'], 'calls': t['usage'].get('api_calls_today', 0)} for t in top_api_users],
                'by_storage': [{'tenant_id': t['tenant_id'], 'name': t['tenant_name'], 'storage_mb': t['usage'].get('storage_mb', 0)} for t in top_storage_users]
            },
            'tenants': [{'tenant_id': t['tenant_id'], 'name': t['tenant_name'], 'health': t['health']['status']} for t in all_tenants_data]
        }
        return json.dumps(summary, indent=2, default=str)

    elif REPORT_FORMAT == 'html':
        # HTML version would go here - for brevity, we'll skip in this example
        return "<!-- HTML report generation would go here -->"

    else:  # Markdown
        report = f"""# Tenant Health Summary Report

**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**Total Tenants:** {total_tenants}

## 📊 Overall Health Distribution
- **🟢 Healthy:** {healthy_count} ({100*healthy_count/max(total_tenants,1):.1f}%)
- **🟡 Warning:** {warning_count} ({100*warning_count/max(total_tenants,1):.1f}%)
- **🔴 Critical:** {critical_count} ({100*critical_count/max(total_tenants,1):.1f}%)
- **⚪ Inactive:** {inactive_count} ({100*inactive_count/max(total_tenants,1):.1f}%)

## 📈 Average Usage Across All Tenants
- **API Usage:** {avg_api_usage:.1f}% of daily limit
- **Storage Usage:** {avg_storage_usage:.1f}% of monthly limit
- **Compute Usage:** {avg_compute_usage:.1f}% of daily limit

## 🏆 Top 5 Users by API Calls Today
"""

        for i, tenant in enumerate(top_api_users, 1):
            report += f"{i}. **{tenant['tenant_name']}** ({tenant['tenant_id']}): {tenant['usage'].get('api_calls_today', 0):,} calls\n"

        report += "\n## 🏆 Top 5 Users by Storage Usage\n"
        for i, tenant in enumerate(top_storage_users, 1):
            report += f"{i}. **{tenant['tenant_name']}** ({tenant['tenant_id']}): {tenant['usage'].get('storage_mb', 0):.1f} MB\n"

        # Add sections for problematic tenants
        if critical_count > 0 or warning_count > 0:
            report += "\n## ⚠️ Tenants Requiring Attention\n"

            problem_tenants = [t for t in all_tenants_data if t['health']['status'] in ['warning', 'critical', 'inactive']]
            problem_tenants.sort(key=lambda x: {'critical': 0, 'warning': 1, 'inactive': 2}.get(x['health']['status'], 3))

            for tenant in problem_tenants[:10]:  # Limit to top 10
                status_emoji = {'critical': '🔴', 'warning': '🟡', 'inactive': '⚪'}.get(tenant['health']['status'], '⚪')
                report += f"- {status_emoji} **{tenant['tenant_name']}** ({tenant['tenant_id']}): {tenant['health']['status'].upper()}"
                if tenant['health']['issues']:
                    report += f" - Issues: {', '.join(tenant['health']['issues'][:2])}"
                report += "\n"

        report += "\n---\n*Report generated automatically by SupremeAI 2.0 Tenant Health Monitor*\n"

        return report

def main() -> int:
    """Main function to generate tenant health reports."""
    print("🏥 Starting Tenant Health Report Generation...")

    # Initialize Firestore client
    db = get_firestore_client()
    if not db:
        print("❌ Failed to initialize Firestore client")
        return 1

    # Get all tenants
    print("🔍 Fetching tenant list...")
    tenants = get_all_tenants(db)

    if not tenants:
        print("⚠️  No tenants found")
        return 1

    print(f"📊 Found {len(tenants)} tenants to analyze")

    # Analyze each tenant
    all_tenants_data = []
    for i, tenant in enumerate(tenants, 1):
        tenant_id = tenant.get('tenant_id', f'unknown_{i}')
        print(f"📋 Analyzing tenant {i}/{len(tenants)}: {tenant_id}")

        # Get usage stats
        usage = get_tenant_usage_stats(db, tenant_id)

        # Get limits
        limits = get_tenant_limits(db, tenant_id)

        # Assess health
        health = assess_tenant_health(usage, limits)

        # Store for reporting
        tenant_data = {
            'tenant': tenant,
            'usage': usage,
            'limits': limits,
            'health': health
        }
        all_tenants_data.append(tenant_data)

    # Generate summary report
    print("\n📝 Generating summary report...")
    summary_report = generate_summary_report(all_tenants_data)

    # Determine recipients
    recipients = []
    if ADMIN_ONLY:
        # Send only to admins
        if REPORT_RECIPIENTS:
            recipients = [r.strip() for r in REPORT_RECIPIENTS.split(",") if r.strip()]
        else:
            # Default admin notification
            admin_email = os.getenv("ADMIN_EMAIL", None)
            if admin_email:
                recipients = [admin_email]
    else:
        # Send to everyone
        if REPORT_RECIPIENTS:
            recipients = [r.strip() for r in REPORT_RECIPIENTS.split(",") if r.strip()]
        # Add individual tenant reports if requested
        if SEND_TENANT_REPORTS:
            for tenant_data in all_tenants_data:
                tenant_email = tenant_data['tenant'].get('email')
                if tenant_email:
                    recipients.append(tenant_email)

    # Remove duplicates
    recipients = list(set(filter(None, recipients)))

    if recipients:
        print(f"\n📧 Sending reports to {len(recipients)} recipient(s)")

        # Send summary report to administrators/recipients
        subject = f"SupremeAI 2.0 Tenant Health Report - {datetime.now().strftime('%Y-%m-%d')}"

        success_count = 0
        for recipient in recipients:
            is_html = (REPORT_FORMAT == 'html')
            if send_report_via_email(recipient, subject, summary_report, is_html):
                success_count += 1

        print(f"✅ Successfully sent reports to {success_count}/{len(recipients)} recipients")

        # If sending individual tenant reports, do those too
        if SEND_TENANT_REPORTS and not ADMIN_ONLY:
            print("\n📧 Sending individual tenant reports...")
            tenant_success = 0
            total_tenant_emails = 0

            for tenant_data in all_tenants_data:
                tenant_email = tenant_data['tenant'].get('email')
                if not tenant_email:
                    continue

                total_tenant_emails += 1
                tenant_id = tenant_data['tenant'].get('tenant_id', 'unknown')
                tenant_name = tenant_data['tenant'].get('display_name', 'Unknown')

                tenant_report = generate_tenant_report(
                    tenant_data['tenant'],
                    tenant_data['usage'],
                    tenant_data['limits'],
                    tenant_data['health']
                )

                subject = f"Your Monthly Usage Report - {tenant_name}"

                if send_report_via_email(tenant_email, subject, tenant_report, (REPORT_FORMAT == 'html')):
                    tenant_success += 1

            print(f"✅ Sent {tenant_success}/{total_tenant_emails} individual tenant reports")
    else:
        # Just output to console/log if no recipients
        print("\n" + "="*60)
        print("SUMMARY REPORT (no email recipients configured)")
        print("="*60)
        print(summary_report)

    print("\n✅ Tenant health report generation completed!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
