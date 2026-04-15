#!/usr/bin/env bash
# bin/provision.sh
#
# Provision AWS resources for a wagtail-wtr site environment.
# Creates one S3 bucket and a dedicated IAM user scoped to that bucket.
# Run once per environment (staging, production).
#
# Usage:
#   bash bin/provision.sh <site-name> [staging|production] [--profile <profile>]
#
# Examples:
#   bash bin/provision.sh mysite production
#   bash bin/provision.sh mysite staging
#   bash bin/provision.sh mysite production --profile my-admin-profile
#
# Invoked via Makefile:
#   make provision SITE=mysite ENV=production
#   make provision SITE=mysite ENV=staging
#   make provision SITE=mysite ENV=production PROFILE=my-admin-profile
#
# ---------------------------------------------------------------------------
# AWS profile setup
# ---------------------------------------------------------------------------
#
# This script uses your local AWS CLI configuration. Before running, ensure
# you have a profile configured with sufficient permissions.
#
# To configure a new profile:
#
#   aws configure --profile wagtail-wtr-provisioner
#
# You will be prompted for:
#   AWS Access Key ID:     <your admin key>
#   AWS Secret Access Key: <your admin secret>
#   Default region name:   us-east-1  (or your preferred region)
#   Default output format: json
#
# Then run:
#   make provision SITE=mysite ENV=production PROFILE=wagtail-wtr-provisioner
#
# Or to use the default profile (configured via `aws configure` with no --profile):
#   make provision SITE=mysite ENV=production
#
# ---------------------------------------------------------------------------
# Required IAM permissions for the profile you use
# ---------------------------------------------------------------------------
#
# The profile must belong to a user or role with the following permissions.
# Create an IAM policy with this document and attach it to your admin user:
#
# {
#   "Version": "2012-10-17",
#   "Statement": [
#     {
#       "Sid": "S3Provisioning",
#       "Effect": "Allow",
#       "Action": [
#         "s3:CreateBucket",
#         "s3:HeadBucket",
#         "s3:PutBucketPolicy",
#         "s3:PutBucketCORS",
#         "s3:PutPublicAccessBlock"
#       ],
#       "Resource": "arn:aws:s3:::*"
#     },
#     {
#       "Sid": "IAMProvisioning",
#       "Effect": "Allow",
#       "Action": [
#         "iam:CreateUser",
#         "iam:GetUser",
#         "iam:PutUserPolicy",
#         "iam:CreateAccessKey",
#         "iam:ListAccessKeys"
#       ],
#       "Resource": "arn:aws:iam::*:user/*"
#     },
#     {
#       "Sid": "STSGetCallerIdentity",
#       "Effect": "Allow",
#       "Action": "sts:GetCallerIdentity",
#       "Resource": "*"
#     }
#   ]
# }
#
# To create this policy in the AWS console:
#   IAM → Policies → Create policy → JSON tab → paste the above → name it
#   "wagtail-wtr-provisioner" → attach to your admin user or group.
#
# Tip: if your admin user already has AdministratorAccess, no extra policy
# is needed — but a scoped policy is safer for shared or CI environments.
# ---------------------------------------------------------------------------

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

SITE=""
ENV="production"
PROFILE="default"
_POSITIONAL=0

# Parse all arguments in a single loop so --profile works regardless of
# whether ENV was supplied or omitted, and in any position relative to flags.
while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)
            PROFILE="${2:-}"
            if [[ -z "$PROFILE" ]]; then
                echo "Error: --profile requires a value." >&2
                exit 1
            fi
            shift 2
            ;;
        -*)
            echo "Error: unknown option '$1'." >&2
            echo "Usage: bash bin/provision.sh <site-name> [staging|production] [--profile <profile>]" >&2
            exit 1
            ;;
        *)
            case "$_POSITIONAL" in
                0) SITE="$1" ;;
                1) ENV="$1"  ;;
                *) echo "Error: unexpected positional argument '$1'." >&2
                   echo "Usage: bash bin/provision.sh <site-name> [staging|production] [--profile <profile>]" >&2
                   exit 1 ;;
            esac
            (( _POSITIONAL++ )) || true
            shift
            ;;
    esac
done

if [[ -z "$SITE" ]]; then
    echo "Error: SITE argument is required." >&2
    echo "Usage: bash bin/provision.sh <site-name> [staging|production] [--profile <profile>]" >&2
    echo "       make provision SITE=mysite ENV=production" >&2
    exit 1
fi

if [[ "$ENV" != "staging" && "$ENV" != "production" ]]; then
    echo "Error: ENV must be 'staging' or 'production' (got: '$ENV')." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Validate SITE: S3 bucket names require lowercase letters, numbers, hyphens;
# must start and end with a letter or number.
# ---------------------------------------------------------------------------

if [[ ! "$SITE" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
    echo "Error: SITE must contain only lowercase letters, numbers, and hyphens," >&2
    echo "       and must start and end with a letter or number (got: '$SITE')." >&2
    exit 1
fi

if [[ "$SITE" == *"--"* ]]; then
    echo "Error: SITE must not contain consecutive hyphens (got: '$SITE')." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Derived resource names
# ---------------------------------------------------------------------------

BUCKET_NAME="${SITE}-wagtail-wtr-${ENV}"
IAM_USER="${SITE}-wagtail-wtr-${ENV}"

# S3 bucket names: max 63 chars. IAM user names: max 64 chars.
# We use the more restrictive S3 limit for both since they share a name.
if [[ "${#BUCKET_NAME}" -gt 63 ]]; then
    echo "Error: derived bucket name '$BUCKET_NAME' is ${#BUCKET_NAME} characters (max 63)." >&2
    echo "Use a shorter site name." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Check dependencies
# ---------------------------------------------------------------------------

if ! command -v aws &>/dev/null; then
    echo "Error: AWS CLI is not installed." >&2
    echo "Install it from: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Verify the profile exists and can authenticate
# ---------------------------------------------------------------------------

echo ""
echo "Using AWS profile: $PROFILE"
echo ""

if ! aws configure list --profile "$PROFILE" &>/dev/null; then
    echo "Error: AWS profile '$PROFILE' is not configured." >&2
    echo "" >&2
    echo "Option 1 — configure this profile:" >&2
    echo "  aws configure --profile $PROFILE" >&2
    echo "" >&2
    echo "  You will be prompted for your AWS Access Key ID, Secret Access Key," >&2
    echo "  default region (e.g. us-east-1), and output format (json)." >&2
    echo "" >&2
    echo "Option 2 — use a different existing profile:" >&2
    echo "  make provision SITE=$SITE ENV=$ENV PROFILE=<your-profile>" >&2
    echo "" >&2
    echo "  To see available profiles: aws configure list-profiles" >&2
    echo "" >&2
    echo "Then re-run:" >&2
    if [[ "$PROFILE" == "default" ]]; then
        echo "  make provision SITE=$SITE ENV=$ENV" >&2
    else
        echo "  make provision SITE=$SITE ENV=$ENV PROFILE=$PROFILE" >&2
    fi
    exit 1
fi

if ! aws sts get-caller-identity --profile "$PROFILE" --output text &>/dev/null; then
    echo "Error: AWS profile '$PROFILE' exists but credentials are invalid or expired." >&2
    echo "" >&2
    echo "To reconfigure it:" >&2
    echo "  aws configure --profile $PROFILE" >&2
    echo "" >&2
    echo "Or use a different profile:" >&2
    echo "  make provision SITE=$SITE ENV=$ENV PROFILE=<your-profile>" >&2
    echo "" >&2
    echo "  To see available profiles: aws configure list-profiles" >&2
    exit 1
fi

CALLER_IDENTITY="$(aws sts get-caller-identity --profile "$PROFILE" --query '[Account,Arn]' --output text)"
ACCOUNT_ID="$(echo "$CALLER_IDENTITY" | awk '{print $1}')"
CALLER_ARN="$(echo "$CALLER_IDENTITY" | awk '{print $2}')"

echo "Authenticated as: $CALLER_ARN"
echo ""

# Get the default region from the profile (used for bucket creation and output)
REGION="$(aws configure get region --profile "$PROFILE" 2>/dev/null || true)"
if [[ -z "$REGION" ]]; then
    echo "Warning: no default region configured for profile '$PROFILE'. Falling back to us-east-1." >&2
    echo "  To set a region: aws configure set region us-east-1 --profile $PROFILE" >&2
    echo "" >&2
    REGION="us-east-1"
fi

# ---------------------------------------------------------------------------
# Confirmation prompt
# ---------------------------------------------------------------------------

echo "About to create the following resources on AWS account $ACCOUNT_ID:"
echo "  Authenticated as: $CALLER_ARN"
echo "  S3 bucket:        $BUCKET_NAME (region: $REGION)"
echo "  IAM user:         $IAM_USER"
echo ""
echo "If this is the wrong account, abort now and re-run with the correct profile."
echo ""
read -r -p "Proceed? [y/N] " CONFIRM
if [[ "${CONFIRM,,}" != "y" ]]; then
    echo "Aborted."
    exit 0
fi
echo ""

# ---------------------------------------------------------------------------
# Helper — all aws commands use --profile
# ---------------------------------------------------------------------------

step() {
    echo "→ $*"
}

aws_cmd() {
    aws --profile "$PROFILE" "$@"
}

# ---------------------------------------------------------------------------
# 1. Create S3 bucket (idempotent — skip if already exists)
# ---------------------------------------------------------------------------

if aws_cmd s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
    step "Bucket $BUCKET_NAME already exists — skipping create"
else
    step "Creating S3 bucket: $BUCKET_NAME (region: $REGION)"
    if [[ "$REGION" == "us-east-1" ]]; then
        # us-east-1 must NOT include --create-bucket-configuration (AWS quirk)
        aws_cmd s3api create-bucket \
            --bucket "$BUCKET_NAME" \
            --region "$REGION" \
            --output text >/dev/null
    else
        aws_cmd s3api create-bucket \
            --bucket "$BUCKET_NAME" \
            --region "$REGION" \
            --create-bucket-configuration "LocationConstraint=$REGION" \
            --output text >/dev/null
    fi
fi

# ---------------------------------------------------------------------------
# 2. Block public ACLs; allow public bucket policy (needed for media reads)
# ---------------------------------------------------------------------------

step "Configuring public access settings on $BUCKET_NAME"

aws_cmd s3api put-public-access-block \
    --bucket "$BUCKET_NAME" \
    --public-access-block-configuration \
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=false,RestrictPublicBuckets=false" \
    --output text >/dev/null

# BlockPublicPolicy=false / RestrictPublicBuckets=false is intentional —
# we apply an explicit bucket policy below that allows public GET for media
# files. Per-object ACL paths are fully blocked above.

# ---------------------------------------------------------------------------
# 3. Create IAM user (idempotent — skip if already exists)
# Must be created before the bucket policy, because AWS validates that the
# Principal ARN in a bucket policy refers to an existing IAM entity.
# ---------------------------------------------------------------------------

if aws_cmd iam get-user --user-name "$IAM_USER" &>/dev/null; then
    step "IAM user $IAM_USER already exists — skipping create"
else
    step "Creating IAM user: $IAM_USER"
    aws_cmd iam create-user \
        --user-name "$IAM_USER" \
        --output text >/dev/null
fi

# ---------------------------------------------------------------------------
# 4. Attach inline IAM policy scoped to this bucket only
# (put-user-policy is idempotent — safe to reapply)
# No PutObjectAcl needed: public access is granted via bucket policy only,
# not per-object ACLs (BlockPublicAcls=true enforces this).
# ---------------------------------------------------------------------------

step "Attaching inline IAM policy to $IAM_USER"

IAM_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3ObjectAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/*"
    },
    {
      "Sid": "S3BucketAccess",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}"
    }
  ]
}
EOF
)

aws_cmd iam put-user-policy \
    --user-name "$IAM_USER" \
    --policy-name "${IAM_USER}-s3-policy" \
    --policy-document "$IAM_POLICY" \
    --output text >/dev/null

# ---------------------------------------------------------------------------
# 5. Apply bucket policy (public GET for all objects; IAM user has access
# via its identity policy above — no need to grant it here too)
# (put-bucket-policy is idempotent — safe to reapply)
# ---------------------------------------------------------------------------

step "Applying bucket policy"

BUCKET_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadMedia",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/*"
    }
  ]
}
EOF
)

aws_cmd s3api put-bucket-policy \
    --bucket "$BUCKET_NAME" \
    --policy "$BUCKET_POLICY" \
    --output text >/dev/null

# ---------------------------------------------------------------------------
# 6. Set CORS policy
# (put-bucket-cors is idempotent — safe to reapply)
# ---------------------------------------------------------------------------

step "Applying CORS policy"

CORS_CONFIG=$(cat <<EOF
{
  "CORSRules": [
    {
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["GET"],
      "AllowedOrigins": ["*"],
      "MaxAgeSeconds": 3000
    }
  ]
}
EOF
)

aws_cmd s3api put-bucket-cors \
    --bucket "$BUCKET_NAME" \
    --cors-configuration "$CORS_CONFIG" \
    --output text >/dev/null

# ---------------------------------------------------------------------------
# 7. Create IAM access keys for the application user
#
# Idempotent: if the user already has 1 or 2 keys, skip creation and instruct
# the operator to rotate manually. AWS allows a maximum of 2 keys per user.
# To rotate: delete the oldest key in the IAM console
#   (IAM → Users → $IAM_USER → Security credentials)
# then re-run this script.
# ---------------------------------------------------------------------------

step "Checking existing access keys for $IAM_USER"

EXISTING_KEY_COUNT="$(aws_cmd iam list-access-keys \
    --user-name "$IAM_USER" \
    --query 'length(AccessKeyMetadata)' \
    --output text)"

APP_ACCESS_KEY_ID=""
APP_SECRET_ACCESS_KEY=""
KEY_CREATED=false

if [[ "$EXISTING_KEY_COUNT" -ge 2 ]]; then
    echo ""
    echo "  IAM user '$IAM_USER' already has 2 access keys (AWS maximum)." >&2
    echo "  Skipping key creation. To rotate credentials:" >&2
    echo "    1. Delete the oldest key: IAM → Users → $IAM_USER → Security credentials" >&2
    echo "    2. Re-run this script." >&2
    echo ""
elif [[ "$EXISTING_KEY_COUNT" -ge 1 ]]; then
    echo ""
    echo "  IAM user '$IAM_USER' already has an access key."
    echo "  Skipping key creation. Credentials were saved to .env.provision.${SITE}.${ENV}"
    echo "  when the key was first created. If that file no longer exists, rotate the key:"
    echo "    1. Delete the existing key: IAM → Users → $IAM_USER → Security credentials"
    echo "    2. Re-run this script to generate a new credentials file."
    echo ""
else
    step "Creating IAM access keys for $IAM_USER"

    KEY_OUTPUT="$(aws_cmd iam create-access-key \
        --user-name "$IAM_USER" \
        --query 'AccessKey.[AccessKeyId,SecretAccessKey]' \
        --output text)"

    APP_ACCESS_KEY_ID="$(echo "$KEY_OUTPUT" | awk '{print $1}')"
    APP_SECRET_ACCESS_KEY="$(echo "$KEY_OUTPUT" | awk '{print $2}')"
    KEY_CREATED=true
fi

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ "$KEY_CREATED" == "true" ]]; then
    # Write credentials to a local file (chmod 600) instead of leaving them
    # in terminal scrollback. The secret cannot be retrieved from AWS after
    # this point.
    CREDS_FILE=".env.provision.${SITE}.${ENV}"
    {
        echo "AWS_STORAGE_BUCKET_NAME=$BUCKET_NAME"
        echo "AWS_S3_REGION_NAME=$REGION"
        echo "AWS_ACCESS_KEY_ID=$APP_ACCESS_KEY_ID"
        echo "AWS_SECRET_ACCESS_KEY=$APP_SECRET_ACCESS_KEY"
    } > "$CREDS_FILE"
    chmod 600 "$CREDS_FILE"

    echo "  Done. Credentials written to: $CREDS_FILE (chmod 600)"
    echo ""
    echo "  Copy these values to your Render dashboard, then delete the file:"
    echo "    cat $CREDS_FILE"
    echo ""
    echo "  WARNING: AWS_SECRET_ACCESS_KEY cannot be retrieved again."
    echo "  Delete the file after copying: rm $CREDS_FILE"
else
    echo "  Done. Bucket and IAM user are configured."
    echo ""
    echo "  No new credentials were created (existing key(s) were preserved)."
    echo "  See instructions above if you need to rotate credentials."
fi

echo ""
echo "  S3 bucket: $BUCKET_NAME (region: $REGION)"
echo "  IAM user:  $IAM_USER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
