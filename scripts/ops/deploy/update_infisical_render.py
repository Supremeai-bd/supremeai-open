from infisical_client import (
    AuthenticationOptions,
    ClientSettings,
    CreateSecretOptions,
    InfisicalClient,
    UniversalAuthMethod,
    UpdateSecretOptions,
)

import os

client_id = os.getenv("INFISICAL_CLIENT_ID", "")
client_secret = os.getenv("INFISICAL_CLIENT_SECRET", "")
project_id = os.getenv("INFISICAL_PROJECT_ID", "")

if not client_id or not project_id:
    raise RuntimeError("INFISICAL_CLIENT_ID and INFISICAL_PROJECT_ID must be provided via environment variables.")

client = InfisicalClient(ClientSettings(
    auth=AuthenticationOptions(
        universal_auth=UniversalAuthMethod(
            client_id=client_id,
            client_secret=client_secret
        )
    )
))

key = 'RENDER_PRIMARY_SVC_ID'
value = os.getenv("RENDER_PRIMARY_SVC_ID", "")
if not value:
    raise RuntimeError("RENDER_PRIMARY_SVC_ID must be set in environment.")

try:
    client.createSecret(options=CreateSecretOptions(
        environment="prod",
        project_id=project_id,
        secret_name=key,
        secret_value=value,
        path="/"
    ))
    print(f"Created {key} in prod")
except Exception:
    try:
        client.updateSecret(options=UpdateSecretOptions(
            environment="prod",
            project_id=project_id,
            secret_name=key,
            secret_value=value,
            path="/"
        ))
        print(f"Updated {key} in prod")
    except Exception as e2:
        print(f"Failed to update {key}: {e2}")
