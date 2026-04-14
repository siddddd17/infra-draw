# infra-draw

> Turn live cloud infrastructure into architecture diagrams — from the terminal.

`infra-draw` connects to your cloud account, discovers resources, and generates
publication-ready architecture diagrams using the
[diagrams](https://diagrams.mingrammer.com/) library.

## Features

| Area | Details |
|------|---------|
| **Cloud-agnostic** | AWS fully implemented; Azure & GCP extension points ready |
| **Rich CLI** | Click-based with coloured output, ASCII banner, progress bars |
| **Interactive shell** | `infra-draw shell` with history, auto-complete, session state |
| **Parallel fetching** | ThreadPoolExecutor + tqdm for fast multi-resource discovery |
| **Tag filtering** | `--exclude-tags env=dev` to skip resources by tag |
| **Per-VPC diagrams** | `--per-vpc` generates one diagram per VPC |
| **Multi-region** | `--all-regions` scans every enabled region |
| **Output formats** | PNG, SVG, PDF via Graphviz |
| **Detail labels** | `--show-details` adds IPs, instance types, CIDRs to nodes |
| **Dry run** | `--dry-run` fetches without generating images |

## Prerequisites

* Python ≥ 3.9
* [Graphviz](https://graphviz.org/download/) (`brew install graphviz` / `apt install graphviz`)
* AWS credentials configured (`aws configure` or environment variables)

## Quick Start

```bash
cd infra_draw
pip install -e ".[dev]"

# Show help and banner
infra-draw

# Generate a diagram for us-east-1
infra-draw generate

# All regions, per-VPC, SVG, with detail labels
infra-draw generate --all-regions --per-vpc --format svg --show-details

# Filter specific resource types
infra-draw generate --resources ec2,vpc,rds

# Exclude staging resources
infra-draw generate --exclude-tags env=staging

# Dry run (discover but don't render)
infra-draw generate --dry-run --verbose

# Interactive shell
infra-draw shell
```

## Interactive Shell

```
infra-draw shell

infra-draw> set region eu-west-1
infra-draw> set per-vpc on
infra-draw> show
infra-draw> generate
infra-draw> list resources
infra-draw> exit
```

## AWS Resource Coverage

| Category | Resources |
|----------|-----------|
| Compute | EC2, Lambda |
| Network | VPC, Subnet, Route Table, IGW, NAT GW, ALB, NLB, VPC Peering, Transit Gateway |
| Database | RDS, DynamoDB |
| Storage | S3 |
| Security | IAM Roles (with attached policies) |

## Project Structure

```
infra_draw/
├── cli/           # Click commands, interactive shell, banner
├── core/          # Config, exceptions, abstract provider interface
├── providers/
│   ├── aws/       # Full implementation (fetchers + diagram builder)
│   ├── azure/     # Stub — ready for extension
│   └── gcp/       # Stub — ready for extension
├── diagram/       # Orchestrator, Graphviz styles
└── utils/         # Logging, progress bars, Graphviz check, tag helpers
```

## Extending to Azure / GCP

1. Create a new module under `providers/<cloud>/`
2. Implement `CloudProvider`, `ResourceFetcher`, and `DiagramBuilder`
3. Decorate the provider class with `@ProviderFactory.register`
4. The CLI auto-discovers it — `infra-draw generate --provider azure`

## Running Tests

```bash
pip install -e ".[dev]"
pytest -v
```

## License

MIT
