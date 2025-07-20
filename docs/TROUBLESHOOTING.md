# MCP Git Server Troubleshooting Guide

## Table of Contents

1. [Common Issues](#common-issues)
2. [Error Diagnostics](#error-diagnostics)
3. [Performance Issues](#performance-issues)
4. [Session Management Problems](#session-management-problems)
5. [Validation Errors](#validation-errors)
6. [Circuit Breaker Issues](#circuit-breaker-issues)
7. [Memory and Resource Leaks](#memory-and-resource-leaks)
8. [Debugging Tools](#debugging-tools)
9. [Log Analysis](#log-analysis)
10. [Recovery Procedures](#recovery-procedures)

## Common Issues

### Server Won't Start

**Symptoms:**
- Server fails to initialize
- Port binding errors
- Import errors

**Diagnosis:**
```python
# Check basic server startup
import asyncio
from mcp_server_git.server import MCPGitServer

async def test_startup():
    try:
        server = MCPGitServer()
        await server.start()
        print("✓ Server started successfully")
        await server.shutdown()
    except Exception as e:
        print(f"✗ Server startup failed: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test_startup())
```

**Solutions:**
1. **Port already in use:**
   ```bash
   # Check what's using the port
   lsof -i :8080

   # Use different port
   export MCP_GIT_PORT=8081
   ```

2. **Missing dependencies:**
   ```bash
   pip install -e .
   pip check
   ```

3. **Permission issues:**
   ```bash
   # Check file permissions
   ls -la src/mcp_server_git/

   # Fix permissions if needed
   chmod +x src/mcp_server_git/__main__.py
   ```

### Client Connection Failures

**Symptoms:**
- Clients can't connect
- Connection drops immediately
- Authentication failures

**Diagnosis:**
```python
# Test client connection
import websockets
import json

async def test_connection():
    try:
        async with websockets.connect("ws://localhost:8080") as websocket:
            # Send test message
            test_msg = {"type": "ping", "id": "test_123"}
            await websocket.send(json.dumps(test_msg))

            # Receive response
            response = await websocket.recv()
            print(f"✓ Connection successful: {response}")
    except Exception as e:
        print(f"✗ Connection failed: {e}")

asyncio.run(test_connection())
```

**Solutions:**
1. **Check server is running:**
   ```bash
   curl -f http://localhost:8080/health || echo "Server not responding"
   ```

2. **Verify network connectivity:**
   ```bash
   telnet localhost 8080
   ```

3. **Check firewall settings:**
   ```bash
   # Linux
   sudo ufw status

   # macOS
   sudo pfctl -sr
   ```

### Message Processing Errors

**Symptoms:**
- Messages not being processed
- Invalid message format errors
- Validation failures

**Diagnosis:**
```python
from mcp_server_git.models.validation import validate_message
from mcp_server_git.models.notifications import CancelledNotification

# Test message validation
test_message = {
    "type": "notifications/cancelled",
    "id": "test_123",
    "request_id": "req_456"
}

result = validate_message(test_message, CancelledNotification)
if not result.is_valid:
    print(f"Validation failed: {result.error}")
else:
    print("✓ Message validation successful")
```

## Error Diagnostics

### Error Classification

**Critical Errors (Require session termination):**
```python
# These errors should close the session
CRITICAL_ERRORS = [
    "authentication_failed",
    "protocol_violation",
    "security_breach",
    "corrupted_session_state"
]

def is_critical_error(error_type):
    return error_type in CRITICAL_ERRORS
```

**Recoverable Errors (Can retry):**
```python
# These errors should trigger retry logic
RECOVERABLE_ERRORS = [
    "network_timeout",
    "temporary_resource_unavailable",
    "rate_limit_exceeded",
    "transient_validation_error"
]

def should_retry(error_type):
    return error_type in RECOVERABLE_ERRORS
```

### Error Pattern Analysis

```python
from collections import defaultdict
from datetime import datetime, timedelta

class ErrorAnalyzer:
    def __init__(self):
        self.error_counts = defaultdict(int)
        self.error_timestamps = defaultdict(list)

    def record_error(self, error_type, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now()

        self.error_counts[error_type] += 1
        self.error_timestamps[error_type].append(timestamp)

    def get_error_rate(self, error_type, window_minutes=60):
        """Get error rate for the last N minutes."""
        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        recent_errors = [
            ts for ts in self.error_timestamps[error_type]
            if ts > cutoff
        ]
        return len(recent_errors) / window_minutes  # errors per minute

    def detect_error_spikes(self, threshold=5):
        """Detect error spikes that might indicate systemic issues."""
        spikes = {}
        for error_type in self.error_counts:
            rate = self.get_error_rate(error_type)
            if rate > threshold:
                spikes[error_type] = rate
        return spikes

# Usage
analyzer = ErrorAnalyzer()

# In your error handler
async def handle_error_with_analysis(error, error_type):
    analyzer.record_error(error_type)

    # Check for error spikes
    spikes = analyzer.detect_error_spikes()
    if spikes:
        logger.warning(f"Error spikes detected: {spikes}")
```

## Performance Issues

### High Latency

**Symptoms:**
- Slow message processing
- Client timeouts
- High response times

**Diagnosis:**
```python
from mcp_server_git.optimizations import PerformanceTimer

# Measure operation performance
async def diagnose_performance():
    with PerformanceTimer("message_processing") as timer:
        # Simulate message processing
        await process_test_message()

    if timer.elapsed_ms > 1000:  # 1 second threshold
        print(f"⚠ High latency detected: {timer.elapsed_ms}ms")
    else:
        print(f"✓ Normal latency: {timer.elapsed_ms}ms")
```

**Solutions:**
1. **Enable validation caching:**
   ```python
   from mcp_server_git.optimizations import enable_validation_cache
   enable_validation_cache()
   ```

2. **Profile bottlenecks:**
   ```python
   from mcp_server_git.optimizations import CPUProfiler

   with CPUProfiler("performance_analysis"):
       await process_messages(large_message_batch)
   ```

3. **Optimize database queries:**
   ```python
   # Use async database operations
   async def get_session_data(session_id):
       async with database.connection() as conn:
           return await conn.fetch_one(
               "SELECT * FROM sessions WHERE id = ?", session_id
           )
   ```

### High Memory Usage

**Symptoms:**
- Memory usage keeps growing
- Out of memory errors
- Slow garbage collection

**Diagnosis:**
```python
from mcp_server_git.optimizations import MemoryMonitor
import gc

def diagnose_memory():
    monitor = MemoryMonitor()

    # Take initial sample
    initial = monitor.take_sample("start")

    # Force garbage collection
    gc.collect()
    after_gc = monitor.take_sample("after_gc")

    print(f"Memory before GC: {initial:.2f}MB")
    print(f"Memory after GC: {after_gc:.2f}MB")
    print(f"GC recovered: {initial - after_gc:.2f}MB")

    # Check for memory leaks
    if initial - after_gc < 10:  # Less than 10MB recovered
        print("⚠ Potential memory leak detected")

    # Get garbage collection stats
    stats = gc.get_stats()
    print(f"GC stats: {stats}")

# Run periodically
asyncio.create_task(periodic_memory_check())

async def periodic_memory_check():
    while True:
        diagnose_memory()
        await asyncio.sleep(300)  # Every 5 minutes
```

**Solutions:**
1. **Clear caches periodically:**
   ```python
   from mcp_server_git.optimizations import clear_validation_cache

   async def cache_cleanup_task():
       while True:
           await asyncio.sleep(3600)  # Every hour
           clear_validation_cache()
           gc.collect()
   ```

2. **Limit session count:**
   ```python
   class MemoryAwareSessionManager(SessionManager):
       MAX_SESSIONS = 1000

       async def create_session(self, session_id=None):
           if len(self.sessions) >= self.MAX_SESSIONS:
               # Close oldest sessions
               await self.cleanup_oldest_sessions(count=100)

           return await super().create_session(session_id)
   ```

### High CPU Usage

**Symptoms:**
- CPU usage constantly high
- Server becomes unresponsive
- Slow message processing

**Diagnosis:**
```python
import psutil
import asyncio
from datetime import datetime

async def monitor_cpu_usage():
    """Monitor CPU usage and identify bottlenecks."""
    while True:
        cpu_percent = psutil.cpu_percent(interval=1)

        if cpu_percent > 80:  # High CPU threshold
            # Get detailed CPU info
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg()

            logger.warning(f"High CPU usage detected", extra={
                "cpu_percent": cpu_percent,
                "cpu_count": cpu_count,
                "load_average": load_avg,
                "timestamp": datetime.now().isoformat()
            })

            # Get process-specific CPU usage
            process = psutil.Process()
            process_cpu = process.cpu_percent()
            threads = process.num_threads()

            logger.warning(f"Process CPU usage: {process_cpu}%, Threads: {threads}")

        await asyncio.sleep(10)  # Check every 10 seconds
```

**Solutions:**
1. **Use async operations:**
   ```python
   # Instead of blocking operations
   def blocking_operation():
       time.sleep(1)  # Bad - blocks event loop

   # Use async alternatives
   async def async_operation():
       await asyncio.sleep(1)  # Good - yields control
   ```

2. **Implement backpressure:**
   ```python
   class BackpressureAwareServer(MCPGitServer):
       def __init__(self):
           super().__init__()
           self.processing_semaphore = asyncio.Semaphore(10)  # Max 10 concurrent

       async def handle_message(self, message, session):
           async with self.processing_semaphore:
               return await super().handle_message(message, session)
   ```

## Session Management Problems

### Sessions Not Cleaning Up

**Symptoms:**
- Growing number of inactive sessions
- Memory usage increasing over time
- Performance degradation

**Diagnosis:**
```python
async def diagnose_session_cleanup():
    sessions = await session_manager.get_all_sessions()

    active_sessions = [s for s in sessions if s.is_active]
    idle_sessions = [s for s in sessions if s.idle_time > 3600]  # 1 hour
    error_sessions = [s for s in sessions if s.state == SessionState.ERROR]

    print(f"Total sessions: {len(sessions)}")
    print(f"Active sessions: {len(active_sessions)}")
    print(f"Idle sessions (>1h): {len(idle_sessions)}")
    print(f"Error sessions: {len(error_sessions)}")

    if len(idle_sessions) > 100:
        print("⚠ Too many idle sessions - cleanup needed")
```

**Solutions:**
1. **Implement aggressive cleanup:**
   ```python
   async def aggressive_session_cleanup():
       while True:
           # Clean up idle sessions more frequently
           closed = await session_manager.cleanup_idle_sessions(max_idle_time=1800)  # 30 min

           if closed > 0:
               logger.info(f"Cleaned up {closed} idle sessions")

           await asyncio.sleep(300)  # Every 5 minutes
   ```

2. **Fix heartbeat mechanism:**
   ```python
   # Ensure heartbeat manager is working
   if not heartbeat_manager.running:
       logger.error("Heartbeat manager not running - restarting")
       await heartbeat_manager.start()
   ```

### Heartbeat Failures

**Symptoms:**
- Sessions timing out unexpectedly
- Clients getting disconnected
- Heartbeat messages not processed

**Diagnosis:**
```python
async def diagnose_heartbeat_system():
    # Check heartbeat manager status
    if not heartbeat_manager.running:
        print("✗ Heartbeat manager not running")
        return

    # Check heartbeat intervals
    print(f"Heartbeat interval: {heartbeat_manager.heartbeat_interval}s")
    print(f"Missed threshold: {heartbeat_manager.missed_heartbeat_threshold}")

    # Check recent heartbeats
    for session_id, last_heartbeat in heartbeat_manager.session_heartbeats.items():
        time_since = (datetime.now() - last_heartbeat).total_seconds()
        if time_since > heartbeat_manager.heartbeat_interval * 2:
            print(f"⚠ Session {session_id} hasn't sent heartbeat in {time_since}s")
```

**Solutions:**
1. **Adjust heartbeat parameters:**
   ```python
   # More tolerant heartbeat settings
   heartbeat_manager = HeartbeatManager(
       session_manager=session_manager,
       heartbeat_interval=60.0,        # Longer interval
       missed_heartbeat_threshold=5    # More tolerance
   )
   ```

2. **Implement heartbeat recovery:**
   ```python
   async def recover_heartbeat_failures():
       """Attempt to recover from heartbeat failures."""
       sessions = await session_manager.get_all_sessions()

       for session in sessions:
           if session.session_id not in heartbeat_manager.session_heartbeats:
               # Re-initialize heartbeat for this session
               await heartbeat_manager.record_heartbeat(session.session_id)
               logger.info(f"Recovered heartbeat for session {session.session_id}")
   ```

## Validation Errors

### Message Format Issues

**Symptoms:**
- Validation errors for valid-looking messages
- Inconsistent validation results
- Unknown field errors

**Diagnosis:**
```python
from mcp_server_git.models.enhanced_validation import enhanced_validate_message

def diagnose_validation_error(message_data):
    # Try different validation modes
    strict_result = enhanced_validate_message(message_data, strict_mode=True)
    lenient_result = enhanced_validate_message(message_data, strict_mode=False)

    print(f"Strict validation: {'✓' if strict_result.is_valid else '✗'}")
    print(f"Lenient validation: {'✓' if lenient_result.is_valid else '✗'}")

    if not strict_result.is_valid:
        print(f"Strict errors: {strict_result.error}")

    if not lenient_result.is_valid:
        print(f"Lenient errors: {lenient_result.error}")

    # Show validation warnings
    if hasattr(lenient_result, 'validation_warnings'):
        print(f"Warnings: {lenient_result.validation_warnings}")
```

**Solutions:**
1. **Use enhanced validation:**
   ```python
   # Enable fallback validation
   from mcp_server_git.models.enhanced_validation import enhanced_validate_message

   result = enhanced_validate_message(data, strict_mode=False)
   if result.is_valid:
       # Process even if there were minor validation issues
       return await process_message(result.model)
   ```

2. **Log validation details:**
   ```python
   def log_validation_failure(message_data, error):
       logger.error("Validation failed", extra={
           "message_type": message_data.get("type", "unknown"),
           "message_id": message_data.get("id", "unknown"),
           "error_type": type(error).__name__,
           "error_details": str(error),
           "message_keys": list(message_data.keys())
       })
   ```

## Circuit Breaker Issues

### Circuit Stuck Open

**Symptoms:**
- Operations failing with "circuit open" errors
- Circuit not recovering automatically
- All requests being rejected

**Diagnosis:**
```python
def diagnose_circuit_breaker(circuit):
    print(f"Circuit: {circuit.name}")
    print(f"State: {circuit.state.value}")
    print(f"Failure count: {circuit.failure_count}")
    print(f"Failure threshold: {circuit.failure_threshold}")
    print(f"Last failure time: {circuit.last_failure_time}")
    print(f"Recovery timeout: {circuit.recovery_timeout}")

    if circuit.state == CircuitState.OPEN:
        time_since_failure = time.time() - circuit.last_failure_time
        print(f"Time since last failure: {time_since_failure}s")

        if time_since_failure > circuit.recovery_timeout:
            print("⚠ Circuit should have moved to half-open by now")
```

**Solutions:**
1. **Manual circuit reset:**
   ```python
   # Reset circuit if it's stuck
   if circuit.state == CircuitState.OPEN:
       time_since_failure = time.time() - circuit.last_failure_time
       if time_since_failure > circuit.recovery_timeout * 2:  # Double timeout
           logger.warning(f"Manually resetting stuck circuit: {circuit.name}")
           circuit.reset()
   ```

2. **Adjust circuit parameters:**
   ```python
   # More lenient circuit breaker
   circuit = CircuitBreaker(
       name="operations",
       failure_threshold=10,     # Higher threshold
       recovery_timeout=60.0,    # Longer recovery time
       half_open_max_calls=3     # More test calls
   )
   ```

## Memory and Resource Leaks

### Detecting Memory Leaks

```python
import tracemalloc
import gc
from mcp_server_git.optimizations import MemoryMonitor

class MemoryLeakDetector:
    def __init__(self):
        self.monitor = MemoryMonitor()
        self.snapshots = []

    def start_tracking(self):
        """Start memory leak detection."""
        tracemalloc.start()
        self.monitor.take_sample("leak_detection_start")

    def take_snapshot(self, label):
        """Take a memory snapshot."""
        gc.collect()  # Force garbage collection

        snapshot = tracemalloc.take_snapshot()
        memory_mb = self.monitor.take_sample(label)

        self.snapshots.append({
            "label": label,
            "snapshot": snapshot,
            "memory_mb": memory_mb,
            "timestamp": datetime.now()
        })

        return memory_mb

    def analyze_leaks(self):
        """Analyze potential memory leaks."""
        if len(self.snapshots) < 2:
            return

        # Compare first and last snapshots
        first = self.snapshots[0]
        last = self.snapshots[-1]

        # Memory growth analysis
        growth = last["memory_mb"] - first["memory_mb"]
        print(f"Memory growth: {growth:.2f}MB")

        # Top memory allocations
        top_stats = last["snapshot"].compare_to(
            first["snapshot"], 'lineno'
        )

        print("Top 10 memory allocations:")
        for stat in top_stats[:10]:
            print(f"  {stat}")

    def get_top_allocators(self, count=10):
        """Get top memory allocators."""
        if not self.snapshots:
            return []

        snapshot = self.snapshots[-1]["snapshot"]
        top_stats = snapshot.statistics('lineno')

        return [(stat.traceback, stat.size) for stat in top_stats[:count]]

# Usage
leak_detector = MemoryLeakDetector()
leak_detector.start_tracking()

# In your main loop
async def memory_monitoring_loop():
    while True:
        leak_detector.take_snapshot(f"periodic_{datetime.now().isoformat()}")

        if len(leak_detector.snapshots) > 10:
            leak_detector.analyze_leaks()
            # Keep only last 5 snapshots
            leak_detector.snapshots = leak_detector.snapshots[-5:]

        await asyncio.sleep(600)  # Every 10 minutes
```

### Resource Cleanup

```python
class ResourceManager:
    def __init__(self):
        self.active_resources = {}
        self.resource_count = 0

    async def acquire_resource(self, resource_type, resource_id=None):
        """Acquire a resource with automatic cleanup."""
        if resource_id is None:
            resource_id = f"{resource_type}_{self.resource_count}"
            self.resource_count += 1

        # Create resource
        if resource_type == "file":
            resource = await self._create_file_resource(resource_id)
        elif resource_type == "connection":
            resource = await self._create_connection_resource(resource_id)
        else:
            raise ValueError(f"Unknown resource type: {resource_type}")

        self.active_resources[resource_id] = {
            "resource": resource,
            "type": resource_type,
            "created_at": datetime.now()
        }

        return resource_id, resource

    async def release_resource(self, resource_id):
        """Release a specific resource."""
        if resource_id not in self.active_resources:
            logger.warning(f"Resource {resource_id} not found for release")
            return

        resource_info = self.active_resources[resource_id]
        resource = resource_info["resource"]

        # Type-specific cleanup
        if resource_info["type"] == "file":
            await self._cleanup_file_resource(resource)
        elif resource_info["type"] == "connection":
            await self._cleanup_connection_resource(resource)

        del self.active_resources[resource_id]
        logger.debug(f"Released resource {resource_id}")

    async def cleanup_old_resources(self, max_age_seconds=3600):
        """Clean up resources older than specified age."""
        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)

        to_cleanup = [
            resource_id for resource_id, info in self.active_resources.items()
            if info["created_at"] < cutoff
        ]

        for resource_id in to_cleanup:
            await self.release_resource(resource_id)

        return len(to_cleanup)
```

## Debugging Tools

### Debug Mode Setup

```python
import logging
from mcp_server_git.logging_config import setup_debug_logging

# Enable comprehensive debug logging
setup_debug_logging()

# Set specific component log levels
logging.getLogger("mcp_server_git.session").setLevel(logging.DEBUG)
logging.getLogger("mcp_server_git.validation").setLevel(logging.DEBUG)
logging.getLogger("mcp_server_git.error_handling").setLevel(logging.DEBUG)
```

### Interactive Debugging

```python
import pdb
from mcp_server_git.server import MCPGitServer

class DebuggableMCPServer(MCPGitServer):
    async def handle_message(self, message, session):
        if os.getenv("MCP_DEBUG_BREAKPOINT"):
            pdb.set_trace()  # Interactive debugging

        return await super().handle_message(message, session)
```

### Performance Profiling

```python
import cProfile
import pstats
from mcp_server_git.optimizations import CPUProfiler

# Profile specific operations
def profile_operation(operation_name, func, *args, **kwargs):
    profiler = cProfile.Profile()
    profiler.enable()

    try:
        result = func(*args, **kwargs)
        return result
    finally:
        profiler.disable()

        # Save profile data
        profiler.dump_stats(f"{operation_name}_profile.stats")

        # Print top functions
        stats = pstats.Stats(profiler)
        stats.sort_stats('tottime')
        stats.print_stats(10)  # Top 10 functions
```

## Recovery Procedures

### Server Recovery

```python
async def emergency_server_recovery():
    """Emergency recovery procedure for server issues."""
    logger.info("Starting emergency server recovery")

    try:
        # 1. Stop all active operations
        await stop_all_operations()

        # 2. Clear all caches
        clear_validation_cache()
        gc.collect()

        # 3. Reset circuit breakers
        for circuit in get_all_circuit_breakers():
            circuit.reset()

        # 4. Clean up sessions
        session_manager = get_session_manager()
        sessions = await session_manager.get_all_sessions()
        for session in sessions:
            await session_manager.close_session(session.session_id)

        # 5. Restart critical components
        await restart_heartbeat_manager()
        await restart_validation_system()

        logger.info("Emergency recovery completed successfully")
        return True

    except Exception as e:
        logger.error(f"Emergency recovery failed: {e}")
        return False

async def graceful_restart():
    """Gracefully restart the server."""
    logger.info("Starting graceful server restart")

    # 1. Stop accepting new connections
    await server.stop_accepting_connections()

    # 2. Wait for active operations to complete
    await wait_for_operations_to_complete(timeout=300)  # 5 minutes

    # 3. Save session state if needed
    await save_session_state()

    # 4. Shutdown components
    await server.shutdown()

    # 5. Restart server
    await server.start()

    # 6. Restore session state if needed
    await restore_session_state()

    logger.info("Graceful restart completed")
```

This troubleshooting guide provides comprehensive diagnostics and solutions for common issues that may arise when running the MCP Git Server with enhanced protocol compliance and stability features.
