# MCP Git Server Usage Guide

## Table of Contents

1. [Quick Start](#quick-start)
2. [Installation and Setup](#installation-and-setup)
3. [Basic Usage](#basic-usage)
4. [Advanced Configuration](#advanced-configuration)
5. [Error Handling Patterns](#error-handling-patterns)
6. [Performance Optimization](#performance-optimization)
7. [Monitoring and Debugging](#monitoring-and-debugging)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

## Quick Start

### Basic Server Setup

```python
import asyncio
from mcp_server_git.server import MCPGitServer

async def main():
    server = MCPGitServer()
    await server.start()
    print("MCP Git Server is running...")
    
    # Keep server running until interrupted
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("Shutting down server...")
    finally:
        await server.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

### Client Connection Example

```python
# Example client connection (pseudo-code)
import json
import websockets

async def connect_to_server():
    uri = "ws://localhost:8080"
    async with websockets.connect(uri) as websocket:
        # Send initialization message
        init_message = {
            "type": "initialize",
            "id": "init_123",
            "params": {
                "capabilities": {
                    "cancellation": True,
                    "progress": True
                }
            }
        }
        await websocket.send(json.dumps(init_message))
        
        # Receive response
        response = await websocket.recv()
        print(f"Server response: {response}")
```

## Installation and Setup

### Environment Setup

```bash
# Install dependencies
pip install -e .

# Set environment variables
export MCP_GIT_LOG_LEVEL=INFO
export MCP_GIT_SESSION_TIMEOUT=3600
export MCP_GIT_HEARTBEAT_INTERVAL=30
export MCP_GIT_MAX_CONCURRENT_SESSIONS=100
```

### Development Setup

```python
# Development configuration with enhanced debugging
import logging
from mcp_server_git.server import MCPGitServer
from mcp_server_git.logging_config import setup_logging

# Setup enhanced logging
setup_logging(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    enable_json_logging=True
)

# Create server with debug options
server = MCPGitServer(debug=True)
```

## Basic Usage

### Message Processing

The server handles various MCP message types automatically:

```python
# Notification messages are processed by the NotificationInterceptor
notification = {
    "type": "notifications/cancelled",
    "id": "cancel_123",
    "request_id": "operation_456",
    "reason": "User requested cancellation"
}

# Progress notifications
progress = {
    "type": "notifications/progress",
    "id": "progress_123",
    "request_id": "operation_456",
    "progress": {
        "current": 50,
        "total": 100,
        "message": "Processing files..."
    }
}
```

### Session Management

```python
from mcp_server_git.session import SessionManager

# Create and manage sessions
session_manager = SessionManager()

# Create new session
session = await session_manager.create_session()

# Track session activity
session.record_message()  # Record processed message
session.record_error()    # Record error occurrence
session.add_operation("git_clone_123")  # Track active operation

# Session cleanup
await session_manager.cleanup_idle_sessions(max_idle_time=3600)
```

### Error Handling

```python
from mcp_server_git.error_handling import recoverable, ErrorSeverity

# Automatic retry for transient errors
@recoverable(max_retries=3, backoff_factor=1.5)
async def unreliable_operation():
    # Operation that might fail temporarily
    return await perform_network_request()

# Error classification and handling
try:
    result = await unreliable_operation()
except Exception as e:
    # Log error with appropriate severity
    logger.error(f"Operation failed: {e}", extra={
        "severity": ErrorSeverity.HIGH,
        "operation": "network_request",
        "recoverable": True
    })
```

## Advanced Configuration

### Custom Server Configuration

```python
from mcp_server_git.server import MCPGitServer
from mcp_server_git.session import SessionManager, HeartbeatManager
from mcp_server_git.error_handling import CircuitBreaker

class CustomMCPServer(MCPGitServer):
    def __init__(self):
        super().__init__()
        
        # Custom session manager
        self.session_manager = SessionManager(
            max_sessions=500,
            session_timeout=7200  # 2 hours
        )
        
        # Custom heartbeat manager
        self.heartbeat_manager = HeartbeatManager(
            session_manager=self.session_manager,
            heartbeat_interval=15.0,  # More frequent heartbeats
            missed_heartbeat_threshold=5  # More tolerant of missed beats
        )
        
        # Circuit breakers for different operations
        self.git_circuit = CircuitBreaker(
            name="git_operations",
            failure_threshold=10,
            recovery_timeout=60.0
        )
        
        self.network_circuit = CircuitBreaker(
            name="network_operations", 
            failure_threshold=5,
            recovery_timeout=30.0
        )
    
    async def start(self):
        await super().start()
        await self.heartbeat_manager.start()
        print("Custom MCP Server started with enhanced configuration")
```

### Performance Tuning

```python
from mcp_server_git.optimizations import (
    enable_validation_cache,
    set_cache_size,
    PerformanceTimer
)

# Enable and configure validation caching
enable_validation_cache()
set_cache_size(1000)  # Cache up to 1000 validation results

# Performance monitoring for all operations
class PerformanceAwareMCPServer(MCPGitServer):
    async def handle_message(self, message, session):
        with PerformanceTimer(f"message_{message.get('type', 'unknown')}"):
            return await super().handle_message(message, session)
```

## Error Handling Patterns

### Graceful Degradation

```python
from mcp_server_git.models.enhanced_validation import enhanced_validate_message

async def handle_message_with_fallback(self, raw_message, session):
    """Handle message with graceful degradation on validation errors."""
    
    # Try strict validation first
    result = enhanced_validate_message(raw_message, strict_mode=True)
    
    if result.is_valid:
        return await self.process_validated_message(result.model, session)
    
    # Fall back to lenient validation
    result = enhanced_validate_message(raw_message, strict_mode=False)
    
    if result.is_valid:
        # Log warning about non-strict validation
        logger.warning(f"Message validated with fallback: {result.validation_warnings}")
        return await self.process_validated_message(result.model, session)
    
    # Final fallback: extract critical fields manually
    message_type = raw_message.get("type", "unknown")
    message_id = raw_message.get("id", "unknown")
    
    logger.error(f"Failed to validate {message_type} message {message_id}")
    
    # Send error response to client
    await self.send_error_response(session.session_id, {
        "error": "validation_failed",
        "message": f"Could not validate {message_type} message",
        "original_id": message_id
    })
```

### Circuit Breaker Integration

```python
from mcp_server_git.error_handling import with_circuit_breaker, CircuitOpenError

class RobustGitOperations:
    def __init__(self):
        self.git_circuit = CircuitBreaker("git_ops", failure_threshold=5)
    
    @with_circuit_breaker(self.git_circuit)
    async def perform_git_operation(self, operation_type, **kwargs):
        """Perform git operation with circuit breaker protection."""
        try:
            return await self._execute_git_command(operation_type, **kwargs)
        except Exception as e:
            logger.error(f"Git operation failed: {e}")
            raise
    
    async def safe_git_operation(self, operation_type, **kwargs):
        """Perform git operation with circuit breaker fallback."""
        try:
            return await self.perform_git_operation(operation_type, **kwargs)
        except CircuitOpenError:
            # Circuit is open, return cached result or error
            logger.warning("Git operations circuit is open, using fallback")
            return await self._get_cached_result(operation_type, **kwargs)
```

## Performance Optimization

### Message Validation Caching

```python
from mcp_server_git.optimizations import get_validation_cache_stats

# Monitor cache performance
async def log_cache_stats_periodically():
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        stats = get_validation_cache_stats()
        
        if stats['total'] > 0:
            hit_rate = stats['hits'] / stats['total']
            logger.info(f"Validation cache hit rate: {hit_rate:.2%}", extra={
                "cache_hits": stats['hits'],
                "cache_misses": stats['misses'],
                "cache_size": stats['current_size']
            })
```

### Memory Management

```python
import gc
from mcp_server_git.optimizations import MemoryMonitor

class MemoryEfficientServer(MCPGitServer):
    def __init__(self):
        super().__init__()
        self.memory_monitor = MemoryMonitor()
        
    async def start(self):
        await super().start()
        # Start memory monitoring
        asyncio.create_task(self._monitor_memory())
    
    async def _monitor_memory(self):
        """Monitor memory usage and trigger cleanup when needed."""
        while True:
            current_memory = self.memory_monitor.take_sample("periodic")
            
            # If memory usage is high, force garbage collection
            if current_memory > 100:  # 100MB threshold
                gc.collect()
                logger.warning(f"High memory usage detected: {current_memory:.2f}MB")
            
            await asyncio.sleep(60)  # Check every minute
```

## Monitoring and Debugging

### Structured Logging

```python
import structlog
from mcp_server_git.logging_config import setup_structured_logging

# Setup structured logging
setup_structured_logging()
logger = structlog.get_logger()

# Log with structured data
logger.info("Message processed", 
    message_type="notifications/cancelled",
    session_id="session_123",
    processing_time_ms=45,
    operation_id="git_clone_456"
)
```

### Metrics Collection

```python
from mcp_server_git.metrics import ServerMetrics
import prometheus_client

class MonitoredMCPServer(MCPGitServer):
    def __init__(self):
        super().__init__()
        self.metrics = ServerMetrics()
        
        # Prometheus metrics
        self.message_counter = prometheus_client.Counter(
            'mcp_messages_total',
            'Total number of messages processed',
            ['message_type', 'status']
        )
        
        self.operation_histogram = prometheus_client.Histogram(
            'mcp_operation_duration_seconds',
            'Time spent processing operations',
            ['operation_type']
        )
    
    async def handle_message(self, message, session):
        message_type = message.get('type', 'unknown')
        
        with self.operation_histogram.labels(operation_type=message_type).time():
            try:
                result = await super().handle_message(message, session)
                self.message_counter.labels(
                    message_type=message_type, 
                    status='success'
                ).inc()
                return result
            except Exception as e:
                self.message_counter.labels(
                    message_type=message_type, 
                    status='error'
                ).inc()
                raise
```

### Health Checks

```python
from datetime import datetime, timedelta

class HealthCheckMCPServer(MCPGitServer):
    def __init__(self):
        super().__init__()
        self.start_time = datetime.now()
        self.last_health_check = datetime.now()
    
    async def health_check(self):
        """Perform comprehensive health check."""
        health_status = {
            "status": "healthy",
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "checks": {}
        }
        
        # Check session manager
        sessions = await self.session_manager.get_all_sessions()
        health_status["checks"]["sessions"] = {
            "active_count": len(sessions),
            "status": "ok" if len(sessions) < 1000 else "warning"
        }
        
        # Check circuit breaker status
        health_status["checks"]["circuit_breakers"] = {
            "git_operations": self.git_circuit.state.value,
            "status": "ok" if self.git_circuit.state != CircuitState.OPEN else "error"
        }
        
        # Check memory usage
        memory_mb = self.memory_monitor.take_sample("health_check")
        health_status["checks"]["memory"] = {
            "usage_mb": memory_mb,
            "status": "ok" if memory_mb < 200 else "warning"
        }
        
        self.last_health_check = datetime.now()
        return health_status
```

## Best Practices

### Error Handling

1. **Always classify errors by severity**
```python
from mcp_server_git.error_handling import ErrorSeverity, ErrorContext

# Critical errors should terminate sessions
if error_type == "authentication_failed":
    context = ErrorContext(e, ErrorSeverity.CRITICAL, "auth", session_id)
    await handle_error(context)
```

2. **Use circuit breakers for external dependencies**
```python
# Protect against cascading failures
@with_circuit_breaker(github_api_circuit)
async def call_github_api():
    return await github_client.get_repo_info()
```

3. **Implement graceful degradation**
```python
try:
    # Try primary approach
    result = await primary_operation()
except Exception:
    # Fall back to secondary approach
    result = await fallback_operation()
```

### Performance

1. **Enable validation caching in production**
```python
from mcp_server_git.optimizations import enable_validation_cache

# Always enable in production
enable_validation_cache()
```

2. **Monitor performance metrics**
```python
# Track all operations
with PerformanceTimer("operation_name"):
    await operation()
```

3. **Use asynchronous operations**
```python
# Process multiple operations concurrently
tasks = [process_message(msg) for msg in messages]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

### Session Management

1. **Configure appropriate timeouts**
```python
# Configure based on expected usage patterns
heartbeat_manager = HeartbeatManager(
    heartbeat_interval=30.0,      # Based on network conditions
    missed_heartbeat_threshold=3   # Balance between responsiveness and tolerance
)
```

2. **Clean up resources properly**
```python
async def cleanup_session(self, session_id):
    # Cancel active operations
    session = await self.session_manager.get_session(session_id)
    for op_id in session.active_operations:
        await self.cancel_operation(op_id)
    
    # Close session
    await self.session_manager.close_session(session_id)
```

## Troubleshooting

### Common Issues

#### High Memory Usage

```python
# Debug memory leaks
from mcp_server_git.optimizations import MemoryMonitor

monitor = MemoryMonitor()
monitor.take_sample("start")

# ... perform operations ...

monitor.take_sample("end")
growth = monitor.get_memory_growth()

if growth > 50:  # 50MB threshold
    logger.warning(f"Potential memory leak detected: {growth}MB growth")
    # Log details about active sessions and operations
```

#### Circuit Breaker Tripping

```python
# Check circuit breaker status
if circuit.state == CircuitState.OPEN:
    logger.info(f"Circuit {circuit.name} is open", extra={
        "failure_count": circuit.failure_count,
        "last_failure_time": circuit.last_failure_time,
        "recovery_timeout": circuit.recovery_timeout
    })
    
    # Wait for recovery or manually reset if needed
    if manual_reset_needed:
        circuit.reset()
```

#### Session Management Issues

```python
# Debug session problems
sessions = await session_manager.get_all_sessions()
for session in sessions:
    if session.idle_time > 3600:  # 1 hour
        logger.warning(f"Long idle session detected", extra={
            "session_id": session.session_id,
            "idle_time": session.idle_time,
            "message_count": session.message_count,
            "error_count": session.error_count
        })
```

### Debugging Tools

#### Enable Debug Logging

```python
import logging
from mcp_server_git.logging_config import setup_logging

# Enable debug logging
setup_logging(level=logging.DEBUG)

# Add trace logging for specific components
logging.getLogger("mcp_server_git.session").setLevel(logging.DEBUG)
logging.getLogger("mcp_server_git.validation").setLevel(logging.DEBUG)
```

#### Performance Profiling

```python
from mcp_server_git.optimizations import CPUProfiler

# Profile performance bottlenecks
with CPUProfiler("message_processing"):
    await process_messages(messages)

# Analyze results
# python -m pstats message_processing.stats
```

This usage guide provides comprehensive examples and patterns for effectively using the MCP Git Server's enhanced features.