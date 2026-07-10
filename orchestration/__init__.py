"""Orchestration layer - wires the independently-built agents together
without modifying any of their source files."""
from .pipeline_orchestrator import PipelineOrchestrator

__all__ = ["PipelineOrchestrator"]
