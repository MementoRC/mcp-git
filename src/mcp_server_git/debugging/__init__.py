"""Debugging module for MCP Git Server.

This module provides comprehensive debugging and state inspection capabilities
designed specifically for LLM analysis and human debugging. It enables deep
introspection into system state, performance, and behavior.

Architecture:
    Debugging capabilities are built around several key concepts:
    - State inspection: Capture and analyze component state
    - Performance profiling: Monitor and analyze performance metrics
    - Debug context: Maintain debugging context across operations
    - LLM-friendly reports: Generate reports optimized for LLM analysis

Key components:
    state_inspector: Centralized state inspection and analysis
    debug_context: Context management for debugging operations
    performance_profiler: Performance monitoring and analysis
    llm_reporter: LLM-optimized debugging report generation

Debugging philosophy:
    - Comprehensive visibility: Every component provides state inspection
    - LLM optimization: Reports designed for AI analysis and understanding
    - Performance awareness: Minimal overhead for debugging capabilities
    - Context preservation: Maintain debugging context across operations
    - Actionable insights: Debugging information leads to specific actions

State inspection capabilities:
    - Component state snapshots: Complete state capture at any time
    - State change tracking: Monitor and explain state transitions
    - Performance metrics: Real-time performance monitoring
    - Resource usage: Memory, CPU, and resource utilization tracking
    - Error context: Comprehensive error information and recovery suggestions

LLM-friendly features:
    - Structured reports: Well-organized, machine-readable debugging output
    - Natural language explanations: Human and LLM readable state descriptions
    - Pattern recognition: Identify common patterns and anomalies
    - Recommendation engine: Suggest debugging actions and optimizations
    - Historical analysis: Track patterns over time

Usage examples:
    >>> from mcp_server_git.debugging import StateInspector
    >>> from mcp_server_git.services import GitService
    >>> 
    >>> inspector = StateInspector()
    >>> git_service = GitService(config)
    >>> 
    >>> # Register service for inspection
    >>> inspector.register_component("git_service", git_service)
    >>> 
    >>> # Capture current state
    >>> snapshot = inspector.capture_state_snapshot("git_service")
    >>> 
    >>> # Generate LLM-friendly report
    >>> report = inspector.generate_llm_friendly_report("git_service")
    >>> print(report)

Performance profiling:
    >>> from mcp_server_git.debugging import PerformanceProfiler
    >>> 
    >>> profiler = PerformanceProfiler()
    >>> 
    >>> with profiler.profile_operation("git_commit"):
    ...     result = git_service.commit_changes(...)
    >>> 
    >>> metrics = profiler.get_operation_metrics("git_commit")
    >>> print(f"Average commit time: {metrics.average_duration}ms")

Debug context management:
    >>> from mcp_server_git.debugging import DebugContext
    >>> 
    >>> with DebugContext("user_request_123") as ctx:
    ...     ctx.add_metadata("user_id", "user456")
    ...     ctx.add_metadata("operation", "git_commit")
    ...     
    ...     result = git_service.commit_changes(...)
    ...     
    ...     if result.error:
    ...         ctx.add_error_context(result.error)
    >>> 
    >>> # Debug context automatically captured and available for analysis

Integration with monitoring:
    - Real-time monitoring: Live debugging and monitoring capabilities
    - Alert integration: Debugging information integrated with alerting
    - Dashboard support: Debugging metrics available for dashboards
    - Log integration: Debugging information integrated with structured logs

See also:
    - protocols.debugging_protocol: Interfaces for debugging capabilities
    - metrics: Performance metrics and monitoring
    - logging_config: Integration with structured logging
"""

# Import all debugging components
from .state_inspector import *
from .debug_context import *
from .performance_profiler import *
from .llm_reporter import *

__all__ = [
    # State inspection
    "StateInspector",
    "StateSnapshot", 
    "ComponentStateInspector",
    
    # Debug context
    "DebugContext",
    "DebugContextManager",
    "OperationContext",
    
    # Performance profiling
    "PerformanceProfiler",
    "OperationProfiler", 
    "ResourceMonitor",
    
    # LLM reporting
    "LLMReporter",
    "ReportGenerator",
    "StateAnalyzer",
]