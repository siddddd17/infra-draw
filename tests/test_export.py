"""Tests for the graph model, AWS graph builder, and all exporters."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from xml.etree.ElementTree import fromstring

import pytest

from infra_draw.core.config import InfraDrawConfig
from infra_draw.export.graph import GraphCluster, GraphEdge, GraphNode, InfraGraph
from infra_draw.providers.aws.graph_builder import AWSGraphBuilder

# Ensure all exporters are registered
import infra_draw.export.json_export  # noqa: F401
import infra_draw.export.drawio  # noqa: F401
import infra_draw.export.mermaid  # noqa: F401
import infra_draw.export.plantuml  # noqa: F401
import infra_draw.export.terraform  # noqa: F401
from infra_draw.export import get_exporter
from infra_draw.export.terraform import terraform_mapping


def _cfg(**overrides: Any) -> InfraDrawConfig:
    defaults = dict(
        provider="aws",
        regions=["us-east-1"],
        all_regions=False,
        profile=None,
        resource_types=[],
        exclude_tags={},
        output_dir=Path("output"),
        output_format="json",
        per_vpc=False,
        show_details=False,
        verbose=False,
        dry_run=False,
        max_workers=2,
    )
    defaults.update(overrides)
    return InfraDrawConfig(**defaults)


def _sample_resources() -> Dict[str, List[Dict[str, Any]]]:
    """Minimal but representative resource set covering every type."""
    return {
        "vpc": [
            {
                "VpcId": "vpc-aaa",
                "CidrBlock": "10.0.0.0/16",
                "Tags": [{"Key": "Name", "Value": "main-vpc"}],
                "_region": "us-east-1",
            }
        ],
        "subnet": [
            {
                "SubnetId": "subnet-bbb",
                "VpcId": "vpc-aaa",
                "CidrBlock": "10.0.1.0/24",
                "Tags": [{"Key": "Name", "Value": "public-a"}],
                "_region": "us-east-1",
            }
        ],
        "igw": [
            {
                "InternetGatewayId": "igw-ccc",
                "Attachments": [{"VpcId": "vpc-aaa"}],
                "Tags": [],
                "_region": "us-east-1",
            }
        ],
        "natgw": [],
        "routetable": [
            {
                "RouteTableId": "rtb-ddd",
                "Associations": [{"SubnetId": "subnet-bbb"}],
                "Routes": [{"GatewayId": "igw-ccc", "DestinationCidrBlock": "0.0.0.0/0"}],
                "Tags": [],
                "_region": "us-east-1",
            }
        ],
        "ec2": [
            {
                "InstanceId": "i-eee",
                "InstanceType": "t3.micro",
                "SubnetId": "subnet-bbb",
                "PrivateIpAddress": "10.0.1.10",
                "Tags": [{"Key": "Name", "Value": "web-1"}],
                "_region": "us-east-1",
            }
        ],
        "lambda": [
            {
                "FunctionName": "my-func",
                "Runtime": "python3.12",
                "VpcConfig": {"SubnetIds": ["subnet-bbb"]},
                "Tags": [{"Key": "Name", "Value": "my-func"}],
                "_region": "us-east-1",
            }
        ],
        "alb": [
            {
                "LoadBalancerName": "app-lb",
                "DNSName": "app-lb-123.elb.amazonaws.com",
                "Type": "application",
                "AvailabilityZones": [{"SubnetId": "subnet-bbb"}],
                "_region": "us-east-1",
            }
        ],
        "nlb": [],
        "rds": [
            {
                "DBInstanceIdentifier": "mydb",
                "Engine": "postgres",
                "DBInstanceClass": "db.t3.micro",
                "DBSubnetGroup": {"Subnets": [{"SubnetIdentifier": "subnet-bbb"}]},
                "Tags": [{"Key": "Name", "Value": "mydb"}],
                "_region": "us-east-1",
            }
        ],
        "dynamodb": [
            {
                "TableName": "users",
                "TableArn": "arn:aws:dynamodb:us-east-1:123456789:table/users",
                "Tags": [],
                "_region": "us-east-1",
            }
        ],
        "s3": [
            {"Name": "my-bucket", "Tags": [], "_region": "us-east-1"}
        ],
        "iam": [
            {
                "RoleName": "deploy-role",
                "Arn": "arn:aws:iam::123456789:role/deploy-role",
                "Tags": [],
                "_region": "global",
            }
        ],
        "vpc_peering": [
            {
                "VpcPeeringConnectionId": "pcx-fff",
                "Tags": [],
                "_region": "us-east-1",
            }
        ],
        "tgw": [
            {
                "TransitGatewayId": "tgw-ggg",
                "Tags": [{"Key": "Name", "Value": "hub"}],
                "_region": "us-east-1",
            }
        ],
    }


# ======================================================================
# Graph model
# ======================================================================

class TestInfraGraph:
    def test_to_dict_round_trip(self):
        graph = InfraGraph(title="test", provider="aws", region="us-east-1")
        graph.nodes.append(GraphNode(id="n1", label="Node 1", resource_type="ec2", aws_type="AWS::EC2::Instance"))
        graph.clusters.append(GraphCluster(id="c1", label="VPC", cluster_type="vpc"))
        graph.edges.append(GraphEdge(id="e1", source="n1", target="n1"))

        d = graph.to_dict()
        assert d["title"] == "test"
        assert len(d["nodes"]) == 1
        assert len(d["edges"]) == 1
        assert len(d["clusters"]) == 1

    def test_nodes_in_cluster(self):
        graph = InfraGraph(title="t", provider="aws", region="r")
        graph.nodes.append(GraphNode(id="a", label="A", resource_type="ec2", aws_type="", cluster_id="c1"))
        graph.nodes.append(GraphNode(id="b", label="B", resource_type="s3", aws_type=""))
        assert len(graph.nodes_in_cluster("c1")) == 1
        assert len(graph.standalone_nodes()) == 1


# ======================================================================
# AWS Graph Builder
# ======================================================================

class TestAWSGraphBuilder:
    def test_builds_graph_from_resources(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")

        assert graph.title.startswith("AWS")
        assert graph.provider == "aws"
        assert len(graph.clusters) == 1
        assert graph.clusters[0].id == "vpc-aaa"

        node_types = {n.resource_type for n in graph.nodes}
        assert "ec2" in node_types
        assert "subnet" in node_types
        assert "igw" in node_types
        assert "lambda" in node_types
        assert "alb" in node_types
        assert "rds" in node_types
        assert "dynamodb" in node_types
        assert "s3" in node_types
        assert "iam" in node_types

        assert len(graph.edges) > 0

    def test_vpc_filter(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1", vpc_id="vpc-nonexistent")
        vpc_nodes = [n for n in graph.nodes if n.cluster_id == "vpc-aaa"]
        assert len(vpc_nodes) == 0

    def test_show_details(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(show_details=True), region="us-east-1")
        ec2_node = next(n for n in graph.nodes if n.resource_type == "ec2")
        assert "t3.micro" in ec2_node.label

    def test_edge_types(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        edge_types = {e.edge_type for e in graph.edges}
        assert "placement" in edge_types
        assert "route_association" in edge_types
        assert "route" in edge_types

    def test_standalone_nodes(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        standalone = graph.standalone_nodes()
        standalone_types = {n.resource_type for n in standalone}
        assert "s3" in standalone_types
        assert "dynamodb" in standalone_types
        assert "iam" in standalone_types


# ======================================================================
# JSON Exporter
# ======================================================================

class TestJSONExporter:
    def test_exports_valid_json(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        exporter = get_exporter("json")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test")
            result = exporter.export(graph, path)
            assert result.endswith(".json")
            assert os.path.exists(result)

            with open(result) as f:
                data = json.load(f)

            assert data["version"] == "1.0"
            assert data["generator"] == "infra-draw"
            assert data["provider"] == "aws"
            assert "graph" in data
            assert "terraform" in data
            assert len(data["graph"]["nodes"]) > 0
            assert len(data["terraform"]["resources"]) > 0
            assert len(data["terraform"]["import_commands"]) > 0


# ======================================================================
# Terraform Exporter
# ======================================================================

class TestTerraformExporter:
    def test_mapping_contains_all_types(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        mapping = terraform_mapping(graph)

        tf_types = {r["terraform_type"] for r in mapping["resources"]}
        assert "aws_vpc" in tf_types
        assert "aws_instance" in tf_types
        assert "aws_s3_bucket" in tf_types
        assert "aws_lambda_function" in tf_types
        assert "aws_db_instance" in tf_types

        for cmd in mapping["import_commands"]:
            assert cmd.startswith("terraform import ")

    def test_standalone_export(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        exporter = get_exporter("terraform")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test")
            result = exporter.export(graph, path)
            assert result.endswith(".tf.json")
            assert os.path.exists(result)

            with open(result) as f:
                data = json.load(f)
            assert "resources" in data
            assert "import_commands" in data


# ======================================================================
# Draw.io Exporter
# ======================================================================

class TestDrawioExporter:
    def test_exports_valid_xml(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        exporter = get_exporter("drawio")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test")
            result = exporter.export(graph, path)
            assert result.endswith(".drawio")
            assert os.path.exists(result)

            with open(result, "rb") as f:
                content = f.read()
            root = fromstring(content)
            assert root.tag == "mxfile"

            cells = root.findall(".//mxCell")
            assert len(cells) > 2  # root cells + at least some nodes

    def test_cluster_and_nodes_present(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        exporter = get_exporter("drawio")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test")
            result = exporter.export(graph, path)

            with open(result, "rb") as f:
                root = fromstring(f.read())

            vertices = [c for c in root.findall(".//mxCell") if c.get("vertex") == "1"]
            edges = [c for c in root.findall(".//mxCell") if c.get("edge") == "1"]
            assert len(vertices) > 0
            assert len(edges) > 0

    def test_no_self_reference_parent(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        exporter = get_exporter("drawio")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test")
            result = exporter.export(graph, path)

            with open(result, "rb") as f:
                root = fromstring(f.read())

            for cell in root.findall(".//mxCell"):
                cid = cell.get("id")
                parent = cell.get("parent")
                if cid and parent:
                    assert cid != parent


# ======================================================================
# Mermaid Exporter
# ======================================================================

class TestMermaidExporter:
    def test_exports_valid_mermaid(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        exporter = get_exporter("mermaid")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test")
            result = exporter.export(graph, path)
            assert result.endswith(".mmd")

            with open(result) as f:
                content = f.read()

            assert "graph TB" in content
            assert "subgraph" in content
            assert "end" in content
            assert "-->" in content or "-.->"\
                   in content

    def test_contains_style_classes(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        exporter = get_exporter("mermaid")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test")
            result = exporter.export(graph, path)

            with open(result) as f:
                content = f.read()

            assert "classDef" in content
            assert "cls_ec2" in content


# ======================================================================
# PlantUML Exporter
# ======================================================================

class TestPlantUMLExporter:
    def test_exports_valid_plantuml(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        exporter = get_exporter("plantuml")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test")
            result = exporter.export(graph, path)
            assert result.endswith(".puml")

            with open(result) as f:
                content = f.read()

            assert "@startuml" in content
            assert "@enduml" in content
            assert "!include <awslib/AWSCommon>" in content
            assert "package" in content
            assert "-->" in content or "..>" in content

    def test_contains_aws_macros(self):
        builder = AWSGraphBuilder()
        graph = builder.build(_sample_resources(), _cfg(), region="us-east-1")
        exporter = get_exporter("plantuml")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test")
            result = exporter.export(graph, path)

            with open(result) as f:
                content = f.read()

            assert "EC2(" in content
            assert "RDS(" in content
            assert "SimpleStorageService(" in content


# ======================================================================
# Exporter registry
# ======================================================================

class TestExporterRegistry:
    def test_all_formats_registered(self):
        for fmt in ("json", "drawio", "mermaid", "plantuml", "terraform"):
            exporter = get_exporter(fmt)
            assert exporter.format_id == fmt
            assert exporter.file_extension

    def test_unknown_format_raises(self):
        with pytest.raises(KeyError):
            get_exporter("docx")


# ======================================================================
# Config helpers
# ======================================================================

class TestConfigFormats:
    def test_is_data_format(self):
        for fmt in ("json", "drawio", "mermaid", "plantuml", "terraform", "raw"):
            cfg = _cfg(output_format=fmt)
            assert cfg.is_data_format is True

    def test_image_format_not_data(self):
        for fmt in ("png", "svg", "pdf"):
            cfg = _cfg(output_format=fmt)
            assert cfg.is_data_format is False

    def test_is_raw_format(self):
        assert _cfg(output_format="raw").is_raw_format is True
        for fmt in ("json", "drawio", "mermaid", "plantuml", "terraform", "png"):
            assert _cfg(output_format=fmt).is_raw_format is False


# ======================================================================
# Raw JSON exporter
# ======================================================================

class TestRawJsonExporter:
    def test_raw_export_writes_aggregated_file(self):
        import datetime as dt
        from infra_draw.export.raw_json import export_raw

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _cfg(output_format="raw", output_dir=Path(tmpdir), profile="demo")
            resources = _sample_resources()
            regions_data = {
                "us-east-1": resources,
                "eu-west-1": {
                    "ec2": [{"InstanceId": "i-eu", "LaunchTime": dt.datetime(2024, 1, 1, 12, 0, 0)}],
                },
            }

            path = export_raw(cfg, regions_data, account_id="123456789012")
            assert path.endswith("aws-raw-all-regions.json")
            with open(path) as f:
                payload = json.load(f)

            assert payload["provider"] == "aws"
            assert payload["account_id"] == "123456789012"
            assert payload["profile"] == "demo"
            assert payload["region_count"] == 2
            assert set(payload["regions"].keys()) == {"us-east-1", "eu-west-1"}
            assert payload["total_resources"] > 0
            assert payload["regions"]["eu-west-1"]["ec2"][0]["LaunchTime"].startswith("2024-01-01")

    def test_raw_export_handles_bytes_and_sets(self):
        from infra_draw.export.raw_json import export_raw

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _cfg(output_format="raw", output_dir=Path(tmpdir))
            regions_data = {
                "us-east-1": {
                    "misc": [{"blob": b"hello", "tags": {"a", "b"}}],
                },
            }
            path = export_raw(cfg, regions_data)
            with open(path) as f:
                payload = json.load(f)
            assert payload["regions"]["us-east-1"]["misc"][0]["blob"] == "hello"
            assert payload["regions"]["us-east-1"]["misc"][0]["tags"] == ["a", "b"]
