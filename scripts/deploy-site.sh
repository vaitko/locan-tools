#!/usr/bin/env bash
# Builds the Astro site and publishes it to the locan.ai S3 website bucket behind CloudFront.
#
# Usage:  AWS_PROFILE=podsite-aws-profile ./scripts/deploy-site.sh [--skip-backup]
# Requires: node ≥ 20, aws cli v2, the site's PUBLIC_API_BASE to point at production (default in site/.env.production).
set -euo pipefail
cd "$(dirname "$0")/.."

export AWS_PROFILE="${AWS_PROFILE:-podsite-aws-profile}"
BUCKET="locan.ai"
DISTRIBUTION_ID="E1HVNFQD0LDQBL"
REGION="us-west-2"
SKIP_BACKUP="${1:-}"

echo "=== 1/6 build + link check ==="
( cd site && npm ci --no-audit --no-fund && PUBLIC_SHOW_TODOS=false npm run check )

if [ "$SKIP_BACKUP" != "--skip-backup" ]; then
  echo "=== 2/6 backup current bucket contents ==="
  BACKUP_DIR="backup/site-$(date +%F-%H%M)"
  mkdir -p "$BACKUP_DIR"
  aws s3 sync "s3://$BUCKET" "$BACKUP_DIR" --region "$REGION" --quiet
  echo "backup written to $BACKUP_DIR (git-ignored)"
else
  echo "=== 2/6 backup skipped ==="
fi

echo "=== 3/6 upload ==="
# hashed assets: immutable, long cache
aws s3 sync site/dist/_astro "s3://$BUCKET/_astro" --region "$REGION" --delete \
  --cache-control "public,max-age=31536000,immutable"
# everything else: short cache so HTML/sitemap updates propagate quickly; --delete removes legacy files
aws s3 sync site/dist "s3://$BUCKET" --region "$REGION" --delete --exclude "_astro/*" \
  --cache-control "public,max-age=300"

echo "=== 4/6 website config (index/error docs + 301 routing rules) ==="
aws s3api put-bucket-website --bucket "$BUCKET" --region "$REGION" \
  --website-configuration "file://infra/s3-website.json"

echo "=== 5/6 CloudFront Function: legacy redirects (replaces the stale optimizer→home rule) ==="
CF_FN="locan-generator"
ETAG="$(aws cloudfront describe-function --name "$CF_FN" --query 'ETag' --output text)"
ETAG="$(aws cloudfront update-function --name "$CF_FN" --if-match "$ETAG" \
  --function-config "Comment=locan.ai legacy URL redirects,Runtime=cloudfront-js-2.0" \
  --function-code fileb://infra/cloudfront-redirects.js --query 'ETag' --output text)"
aws cloudfront publish-function --name "$CF_FN" --if-match "$ETAG" --query 'FunctionSummary.Status' --output text

echo "=== 6/6 CloudFront invalidation ==="
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*" \
  --query 'Invalidation.{Id:Id,Status:Status}' --output table

echo
echo "Deployed. Verify: https://locan.ai/  https://locan.ai/tools/  https://locan.ai/GBP-category-optimizer/ (→ 301)"
