"""Tests for rollback script generation."""

import os
import tempfile

from ceph_primary_balancer.models import SwapProposal
from ceph_primary_balancer.script_generator import generate_rollback_script


def _make_swaps():
    return [
        SwapProposal(pgid="1.a1", old_primary=10, new_primary=20, score_improvement=0.5),
        SwapProposal(pgid="1.b2", old_primary=15, new_primary=25, score_improvement=0.3),
        SwapProposal(pgid="2.c3", old_primary=30, new_primary=40, score_improvement=0.7),
    ]


class TestRollbackScriptGeneration:

    def test_rollback_script_created(self):
        swaps = _make_swaps()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_rebalance.sh")
            rollback_path = generate_rollback_script(swaps, output_path)
            assert rollback_path is not None
            assert os.path.exists(rollback_path)

    def test_rollback_script_executable(self):
        swaps = _make_swaps()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_rebalance.sh")
            rollback_path = generate_rollback_script(swaps, output_path)
            assert os.access(rollback_path, os.X_OK)

    def test_rollback_script_has_shebang_and_headers(self):
        swaps = _make_swaps()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_rebalance.sh")
            rollback_path = generate_rollback_script(swaps, output_path)
            with open(rollback_path) as f:
                content = f.read()
            assert content.startswith("#!/bin/bash")
            assert "ROLLBACK" in content
            assert "REVERSE" in content

    def test_rollback_script_has_health_check(self):
        swaps = _make_swaps()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_rebalance.sh")
            rollback_path = generate_rollback_script(swaps, output_path)
            with open(rollback_path) as f:
                content = f.read()
            assert "Checking cluster health" in content
            assert "HEALTH_OK" in content

    def test_rollback_script_has_correct_total(self):
        swaps = _make_swaps()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_rebalance.sh")
            rollback_path = generate_rollback_script(swaps, output_path)
            with open(rollback_path) as f:
                content = f.read()
            assert f"TOTAL={len(swaps)}" in content

    def test_rollback_reverses_swaps(self):
        """Rollback script should map each PG back to its original primary."""
        swaps = _make_swaps()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_rebalance.sh")
            rollback_path = generate_rollback_script(swaps, output_path)
            with open(rollback_path) as f:
                content = f.read()
            for swap in swaps:
                expected = f'apply_mapping "{swap.pgid}" {swap.old_primary}'
                assert expected in content, (
                    f"Expected reversed swap for {swap.pgid}: "
                    f"OSD.{swap.new_primary} -> OSD.{swap.old_primary}"
                )

    def test_empty_swaps_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_rebalance.sh")
            result = generate_rollback_script([], output_path)
            assert result is None
