"""Tests for the quality gate evaluation."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from matcher.pipeline.quality_gate import evaluate_quality_gate


class TestEvaluateQualityGate:
    async def test_no_golden_set_passes(self):
        session = AsyncMock()
        with patch("matcher.pipeline.quality_gate.MetricsRepo") as MockMetricsRepo:
            repo = MockMetricsRepo.return_value
            repo.compute_quality_metrics = AsyncMock(return_value={"total_cases": 0})
            result = await evaluate_quality_gate(session)
        assert result.passed is True

    async def test_no_previous_report_passes(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with patch("matcher.pipeline.quality_gate.MetricsRepo") as MockMetricsRepo:
            repo = MockMetricsRepo.return_value
            repo.compute_quality_metrics = AsyncMock(
                return_value={
                    "total_cases": 100,
                    "top1_accuracy": 0.90,
                    "top3_recall": 0.95,
                    "auto_match_fp_rate": 0.05,
                }
            )
            result = await evaluate_quality_gate(session)
        assert result.passed is True

    async def test_accuracy_drop_within_threshold_passes(self):
        session = AsyncMock()
        prev_report = MagicMock()
        prev_report.top1_accuracy = Decimal("0.92")
        prev_report.top3_recall = Decimal("0.95")
        prev_report.auto_match_fp_rate = Decimal("0.05")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = prev_report
        session.execute.return_value = mock_result

        with patch("matcher.pipeline.quality_gate.MetricsRepo") as MockMetricsRepo:
            repo = MockMetricsRepo.return_value
            repo.compute_quality_metrics = AsyncMock(
                return_value={
                    "total_cases": 100,
                    "top1_accuracy": 0.91,  # 1% drop, within 2% threshold
                    "top3_recall": 0.95,
                    "auto_match_fp_rate": 0.05,
                }
            )
            result = await evaluate_quality_gate(session)
        assert result.passed is True

    async def test_accuracy_drop_exceeds_threshold_fails(self):
        session = AsyncMock()
        prev_report = MagicMock()
        prev_report.top1_accuracy = Decimal("0.92")
        prev_report.top3_recall = Decimal("0.95")
        prev_report.auto_match_fp_rate = Decimal("0.05")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = prev_report
        session.execute.return_value = mock_result

        with patch("matcher.pipeline.quality_gate.MetricsRepo") as MockMetricsRepo:
            repo = MockMetricsRepo.return_value
            repo.compute_quality_metrics = AsyncMock(
                return_value={
                    "total_cases": 100,
                    "top1_accuracy": 0.89,  # 3% drop, exceeds 2% threshold
                    "top3_recall": 0.95,
                    "auto_match_fp_rate": 0.05,
                }
            )
            result = await evaluate_quality_gate(session)
        assert result.passed is False
        assert len(result.regressions) == 1
        assert "accuracy" in result.regressions[0].lower()

    async def test_fp_rate_increase_fails(self):
        session = AsyncMock()
        prev_report = MagicMock()
        prev_report.top1_accuracy = Decimal("0.92")
        prev_report.top3_recall = Decimal("0.95")
        prev_report.auto_match_fp_rate = Decimal("0.05")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = prev_report
        session.execute.return_value = mock_result

        with patch("matcher.pipeline.quality_gate.MetricsRepo") as MockMetricsRepo:
            repo = MockMetricsRepo.return_value
            repo.compute_quality_metrics = AsyncMock(
                return_value={
                    "total_cases": 100,
                    "top1_accuracy": 0.92,
                    "top3_recall": 0.95,
                    "auto_match_fp_rate": 0.07,  # 2% increase, exceeds 1% threshold
                }
            )
            result = await evaluate_quality_gate(session)
        assert result.passed is False
        assert any("fp" in r.lower() for r in result.regressions)

    async def test_fp_rate_uses_false_positive_alias(self):
        session = AsyncMock()
        prev_report = MagicMock()
        prev_report.top1_accuracy = Decimal("0.92")
        prev_report.top3_recall = Decimal("0.95")
        prev_report.auto_match_fp_rate = Decimal("0.05")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = prev_report
        session.execute.return_value = mock_result

        with patch("matcher.pipeline.quality_gate.MetricsRepo") as MockMetricsRepo:
            repo = MockMetricsRepo.return_value
            repo.compute_quality_metrics = AsyncMock(
                return_value={
                    "total_cases": 100,
                    "top1_accuracy": 0.92,
                    "top3_recall": 0.95,
                    "auto_match_false_positive_rate": 0.07,
                }
            )
            result = await evaluate_quality_gate(session)
        assert result.passed is False
        assert any("fp" in r.lower() for r in result.regressions)

    async def test_multiple_regressions_reported(self):
        session = AsyncMock()
        prev_report = MagicMock()
        prev_report.top1_accuracy = Decimal("0.92")
        prev_report.top3_recall = Decimal("0.95")
        prev_report.auto_match_fp_rate = Decimal("0.05")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = prev_report
        session.execute.return_value = mock_result

        with patch("matcher.pipeline.quality_gate.MetricsRepo") as MockMetricsRepo:
            repo = MockMetricsRepo.return_value
            repo.compute_quality_metrics = AsyncMock(
                return_value={
                    "total_cases": 100,
                    "top1_accuracy": 0.89,  # 3% drop
                    "top3_recall": 0.95,
                    "auto_match_fp_rate": 0.07,  # 2% increase
                }
            )
            result = await evaluate_quality_gate(session)
        assert result.passed is False
        assert len(result.regressions) == 2

    async def test_recall_drop_exceeds_threshold_fails(self):
        session = AsyncMock()
        prev_report = MagicMock()
        prev_report.top1_accuracy = Decimal("0.92")
        prev_report.top3_recall = Decimal("0.95")
        prev_report.auto_match_fp_rate = Decimal("0.05")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = prev_report
        session.execute.return_value = mock_result

        with patch("matcher.pipeline.quality_gate.MetricsRepo") as MockMetricsRepo:
            repo = MockMetricsRepo.return_value
            repo.compute_quality_metrics = AsyncMock(
                return_value={
                    "total_cases": 100,
                    "top1_accuracy": 0.92,
                    "top3_recall": 0.91,  # 4% drop, exceeds 3% threshold
                    "auto_match_fp_rate": 0.05,
                }
            )
            result = await evaluate_quality_gate(session)
        assert result.passed is False
        assert len(result.regressions) == 1
        assert "recall" in result.regressions[0].lower()

    async def test_custom_thresholds_relax_gate(self):
        session = AsyncMock()
        prev_report = MagicMock()
        prev_report.top1_accuracy = Decimal("0.92")
        prev_report.top3_recall = Decimal("0.95")
        prev_report.auto_match_fp_rate = Decimal("0.05")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = prev_report
        session.execute.return_value = mock_result

        with patch("matcher.pipeline.quality_gate.MetricsRepo") as MockMetricsRepo:
            repo = MockMetricsRepo.return_value
            repo.compute_quality_metrics = AsyncMock(
                return_value={
                    "total_cases": 100,
                    "top1_accuracy": 0.89,  # 3% drop — would fail at default 2%
                    "top3_recall": 0.95,
                    "auto_match_fp_rate": 0.05,
                }
            )
            # With relaxed threshold of 5%, the 3% drop should pass
            result = await evaluate_quality_gate(session, max_accuracy_drop=0.05)
        assert result.passed is True
        assert len(result.regressions) == 0

    async def test_improvements_are_reported_for_all_metrics(self):
        session = AsyncMock()
        prev_report = MagicMock()
        prev_report.top1_accuracy = Decimal("0.80")
        prev_report.top3_recall = Decimal("0.82")
        prev_report.auto_match_fp_rate = Decimal("0.08")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = prev_report
        session.execute.return_value = mock_result

        with patch("matcher.pipeline.quality_gate.MetricsRepo") as MockMetricsRepo:
            repo = MockMetricsRepo.return_value
            repo.compute_quality_metrics = AsyncMock(
                return_value={
                    "total_cases": 100,
                    "top1_accuracy": 0.84,
                    "top3_recall": 0.87,
                    "auto_match_fp_rate": 0.04,
                }
            )
            result = await evaluate_quality_gate(session)

        assert result.passed is True
        assert len(result.improvements) == 3
