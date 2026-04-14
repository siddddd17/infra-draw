# infra-draw

> Turn live cloud infrastructure into architecture diagrams — from the terminal.

`infra-draw` connects to your cloud account, discovers resources, and generates
publication-ready architecture diagrams using the
[diagrams](https://diagrams.mingrammer.com/) library.

## Features

| Area | Details |
|------|---------|
| **Setup wizard** | Guided first-run: provider selection, CLI install, credential setup |
| **Cloud-agnostic** | AWS fully implemented; Azure & GCP extension points ready |
| **Rich CLI** | Click-based with coloured output, ASCII banner, progress bars |
| **Interactive shell** | `infra-draw shell` with history, auto-complete, session state |
| **Parallel fetching** | ThreadPoolExecutor + tqdm for fast multi-resource discovery |
| **Tag filtering** | `--exclude-tags env=dev` to skip resources by tag |
| **Per-VPC diagrams** | `--per-vpc` generates one diagram per VPC |
| **Multi-region** | `--all-regions` scans every enabled region |
| **Output formats** | PNG, SVG, PDF (Graphviz) + JSON, Draw.io, Mermaid, PlantUML, Terraform |
| **Detail labels** | `--show-details` adds IPs, instance types, CIDRs to nodes |
| **Dry run** | `--dry-run` fetches without generating images |

## Prerequisites

* Python ≥ 3.9
* [Graphviz](https://graphviz.org/download/) (`brew install graphviz` / `apt install graphviz`) — required only for PNG/SVG/PDF
* AWS credentials configured (the setup wizard can handle this for you)

## Getting Started

```bash
pip install -e ".[dev]"

# Launch the interactive setup wizard
infra-draw
```

The wizard walks you through:

1. **Provider selection** — choose AWS (GCP and Azure coming soon)
2. **AWS CLI check** — detects your OS and offers to install it automatically
3. **Profile setup** — lists existing AWS profiles or creates a new one
4. **Credential verification** — tests with `sts get-caller-identity`
5. **Action menu** — generate a diagram, customise options, or do a dry run

Your chosen profile is saved to `~/.infra-draw/config.json` so subsequent runs
skip straight to the action menu.

```
$ infra-draw

  Choose your cloud provider:
    1. AWS
    2. GCP  (coming soon)
    3. Azure (coming soon)

  > 1

  Checking AWS CLI installation …
  AWS CLI found: aws-cli/2.15.0 Python/3.11.6

  Available AWS profiles:
    1  default
    2  prod
    3  dev

  Select a profile (number), or type 'new' to create one: 2

  Testing credentials … Success! Account ID: 123456789012
  Now using profile: prod (account 123456789012)

  What would you like to do?
    1. Generate a diagram (all resources in us-east-1)
    2. Generate a diagram with custom options
    3. View discovered resources (dry run)
    4. Change profile / provider
    5. Exit
```

To re-run the wizard at any time:

```bash
infra-draw setup          # run the wizard
infra-draw setup --reset  # clear saved config and start fresh
```

## Non-Interactive Usage (CI / scripts)

`infra-draw generate` remains fully non-interactive and respects the saved
profile automatically:

```bash
# Generate a diagram for us-east-1
infra-draw generate

# All regions, per-VPC, SVG, with detail labels
infra-draw generate --all-regions --per-vpc --format svg --show-details

# Filter specific resource types
infra-draw generate --resources ec2,vpc,rds

# Exclude staging resources
infra-draw generate --exclude-tags env=staging

# Data exports (no Graphviz required)
infra-draw generate --format json
infra-draw generate --format drawio
infra-draw generate --format mermaid
infra-draw generate --format plantuml
infra-draw generate --format terraform

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
infra-draw> set format mermaid
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
├── cli/           # Click commands, setup wizard, interactive shell
├── core/          # Config, saved config, exceptions, abstract provider interface
├── export/        # Graph model and exporters (JSON, Draw.io, Mermaid, PlantUML, Terraform)
├── providers/
│   ├── aws/       # Full implementation (fetchers + diagram/graph builders)
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
