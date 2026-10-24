#!/bin/bash
# setup_kms.sh
# Script to generate a local Fernet key for SupremeAI 2.0 local development

echo "Generating local Fernet key for credential encryption..."
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not installed. Aborting."
    exit 1
fi

KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null)
if [ $? -ne 0 ]; then
    echo "Failed to generate key. Ensure 'cryptography' package is installed: pip install cryptography"
    exit 1
fi

echo "Your Local Fernet Key is:"
echo "$KEY"
echo ""
echo "Please add this to your local .env file:"
echo "SUPREMEAI_CREDENTIAL_ENC_KEY=$KEY"
echo "ENCRYPTION_KEY=$KEY"
