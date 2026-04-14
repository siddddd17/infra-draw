#!/usr/bin/env bash
# ── infra-draw usage examples ──────────────────────────────────────────

set -euo pipefail

# Install in editable mode
pip install -e ".[dev]"

# 1. Show banner and help
infra-draw
infra-draw --help

# 2. Show version
infra-draw version

# 3. Basic diagram generation (default: us-east-1, png)
infra-draw generate

# 4. Specific region with AWS profile
infra-draw generate --region eu-west-1 --profile production

# 5. All regions, SVG output, with detail labels
infra-draw generate --all-regions --format svg --show-details

# 6. Per-VPC diagrams, exclude dev resources
infra-draw generate --per-vpc --exclude-tags env=dev --exclude-tags team=sandbox

# 7. Only specific resource types
infra-draw generate --resources ec2,vpc,rds,s3

# 8. Dry run with verbose logging
infra-draw generate --dry-run --verbose

# 9. Custom output directory, PDF format
infra-draw generate --output-dir /tmp/infra-diagrams --format pdf

# 10. Interactive shell
infra-draw shell
