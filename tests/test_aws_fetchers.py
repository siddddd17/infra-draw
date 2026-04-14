"""Unit tests for AWS fetchers – uses moto to mock boto3."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from infra_draw.core.config import InfraDrawConfig
from infra_draw.providers.aws.fetchers.compute import ComputeFetcher
from infra_draw.providers.aws.fetchers.network import NetworkFetcher
from infra_draw.providers.aws.fetchers.database import DatabaseFetcher
from infra_draw.providers.aws.fetchers.storage import StorageFetcher
from infra_draw.providers.aws.fetchers.security import SecurityFetcher


def _cfg(**overrides) -> InfraDrawConfig:
    defaults = dict(
        provider="aws",
        regions=["us-east-1"],
        all_regions=False,
        profile=None,
        resource_types=[],
        exclude_tags={},
        output_dir="output",
        output_format="png",
        per_vpc=False,
        show_details=False,
        verbose=False,
        dry_run=False,
        max_workers=2,
    )
    defaults.update(overrides)
    return InfraDrawConfig(**defaults)


# ── EC2 ──────────────────────────────────────────────────────────────
@mock_aws
class TestComputeFetcher:
    def _setup_ec2(self):
        ec2 = boto3.client("ec2", region_name="us-east-1")
        ec2.run_instances(
            ImageId="ami-12345678",
            MinCount=2,
            MaxCount=2,
            InstanceType="t2.micro",
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [{"Key": "Name", "Value": "web-server"}],
                }
            ],
        )
        return boto3.Session()

    def test_fetch_ec2_instances(self):
        session = self._setup_ec2()
        fetcher = ComputeFetcher(session)
        result = fetcher.fetch(_cfg())
        assert "ec2" in result
        assert len(result["ec2"]) == 2
        assert result["ec2"][0]["_region"] == "us-east-1"

    def test_exclude_tags_filters_instances(self):
        session = self._setup_ec2()
        fetcher = ComputeFetcher(session)
        cfg = _cfg(exclude_tags={"Name": "web-server"})
        result = fetcher.fetch(cfg)
        assert result.get("ec2", []) == []

    def test_resource_type_filtering(self):
        session = self._setup_ec2()
        fetcher = ComputeFetcher(session)
        cfg = _cfg(resource_types=["lambda"])
        result = fetcher.fetch(cfg)
        assert "ec2" not in result


# ── VPC / Network ────────────────────────────────────────────────────
@mock_aws
class TestNetworkFetcher:
    def test_fetch_vpcs(self):
        session = boto3.Session()
        ec2 = session.client("ec2", region_name="us-east-1")
        ec2.create_vpc(CidrBlock="10.0.0.0/16")

        fetcher = NetworkFetcher(session)
        result = fetcher.fetch(_cfg())
        # moto creates a default VPC + our VPC
        assert "vpc" in result
        assert len(result["vpc"]) >= 1

    def test_fetch_subnets(self):
        session = boto3.Session()
        ec2 = session.client("ec2", region_name="us-east-1")
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        vpc_id = vpc["Vpc"]["VpcId"]
        ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")

        fetcher = NetworkFetcher(session)
        result = fetcher.fetch(_cfg())
        assert "subnet" in result
        assert any(s.get("CidrBlock") == "10.0.1.0/24" for s in result["subnet"])


# ── Database ─────────────────────────────────────────────────────────
@mock_aws
class TestDatabaseFetcher:
    def test_fetch_dynamodb_tables(self):
        session = boto3.Session()
        ddb = session.client("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="users",
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        fetcher = DatabaseFetcher(session)
        result = fetcher.fetch(_cfg())
        assert "dynamodb" in result
        assert any(t.get("TableName") == "users" for t in result["dynamodb"])


# ── Storage ──────────────────────────────────────────────────────────
@mock_aws
class TestStorageFetcher:
    def test_fetch_s3_buckets(self):
        session = boto3.Session()
        s3 = session.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="my-test-bucket")

        fetcher = StorageFetcher(session)
        result = fetcher.fetch(_cfg())
        assert "s3" in result
        assert any(b.get("Name") == "my-test-bucket" for b in result["s3"])


# ── Security ─────────────────────────────────────────────────────────
@mock_aws
class TestSecurityFetcher:
    def test_fetch_iam_roles(self):
        session = boto3.Session()
        iam = session.client("iam")
        iam.create_role(
            RoleName="test-role",
            AssumeRolePolicyDocument="{}",
            Path="/",
        )
        fetcher = SecurityFetcher(session)
        result = fetcher.fetch(_cfg())
        assert "iam" in result
        assert any(r.get("RoleName") == "test-role" for r in result["iam"])
