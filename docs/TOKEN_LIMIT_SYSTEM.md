# Token Limit Protection System

A comprehensive token limit protection and content optimization system for the MCP Git Server that prevents overwhelming LLM clients while preserving semantic meaning and technical accuracy.

## Overview

The Token Limit Protection System addresses the critical issue of LLM clients being overwhelmed by large git operation responses (diffs, logs, status, etc.) that can exceed ~25K token limits, causing retries and poor performance. The system provides:

- **Intelligent Token Estimation**: Accurate token counting for different content types
- **Smart Content Truncation**: Semantic-preserving truncation strategies per operation type
- **LLM-Optimized Formatting**: Removes human-friendly elements (emojis, verbose messages) for LLM clients
- **Client Detection**: Automatically detects and serves appropriate content to LLMs vs humans
- **Configurable Limits**: Per-client and per-operation token limits
- **Non-Invasive Integration**: Middleware-based approach requires no changes to existing git operations

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   Git Operation │    │ TokenLimit       │    │   Client            │
│   (diff, log,   │───▶│ Middleware       │───▶│   (LLM/Human)       │
│   status, etc.) │    │                  │    │                     │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
                                │
                                ▼
                  ┌─────────────────────────────────┐
                  │        Core Components          │
                  │                                 │
                  │  • TokenEstimator               │
                  │  • ClientDetector               │
                  │  • ContentOptimizer             │
                  │  • IntelligentTruncationManager │
                  │  • ConfigurationManager         │
                  └─────────────────────────────────┘
```

### Core Components

1. **TokenLimitMiddleware**: Main middleware that intercepts responses and applies optimizations
2. **TokenEstimator**: Estimates token usage for different content types (text, code, diffs, logs)
3. **ClientDetector**: Identifies LLM vs human clients from request metadata
4. **ContentOptimizer**: Converts human-friendly output to LLM-optimized format
5. **IntelligentTruncationManager**: Operation-aware truncation with semantic preservation
6. **ConfigurationManager**: Flexible configuration from files, environment, or code

## Key Features

### Intelligent Token Estimation
- **Content-Type Aware**: Different ratios for text (~4 chars/token), code (~3 chars/token), diffs (~2.5 chars/token)
- **Confidence Scoring**: Provides confidence levels for estimates
- **Performance Optimized**: Fast estimation with minimal overhead

### Operation-Specific Truncation
- **git_diff**: Preserves file headers, function signatures, truncates large changes intelligently
- **git_log**: Keeps recent commits, summarizes older entries
- **git_status**: Prioritizes staged changes, groups similar files
- **github_get_pr_files**: Limits file count, excludes large binary diffs
- **Generic**: Fallback strategy for unknown operations

### Client-Aware Content Optimization
- **LLM Clients**: Removes emojis, simplifies verbose messages, optimizes structure
- **Human Clients**: Preserves full formatting and visual elements
- **Unknown Clients**: Conservative optimizations

### Flexible Configuration
- **Multiple Sources**: Configuration files, environment variables, programmatic settings
- **Predefined Profiles**: Conservative, balanced, aggressive, development profiles
- **Operation Overrides**: Custom token limits per git operation
- **Runtime Updates**: Dynamic configuration updates without restart

## Installation & Integration

### 1. Basic Integration

The system integrates seamlessly with the existing middleware framework:

```python
from mcp_server_git.frameworks.server_middleware import create_enhanced_middleware_chain
from mcp_server_git.middlewares.token_limit import create_token_limit_middleware

# Create enhanced middleware chain with token limits
chain = create_enhanced_middleware_chain(enable_token_limits=True)

# Or add manually to existing chain
token_middleware = create_token_limit_middleware(
    llm_token_limit=20000,
    enable_optimization=True,
    enable_truncation=True
)
chain.add_middleware(token_middleware)
```

### 2. Configuration

#### Environment Variables
```bash
export MCP_GIT_LLM_TOKEN_LIMIT=20000
export MCP_GIT_ENABLE_OPTIMIZATION=true
export MCP_GIT_ENABLE_TRUNCATION=true
export MCP_GIT_FORCE_CLIENT_TYPE=llm  # Force LLM mode
export MCP_GIT_OPERATION_LIMIT_GIT_DIFF=25000
```

#### Configuration File (config/token_limits.json)
```json
{
  "token_limits": {
    "llm_token_limit": 20000,
    "human_token_limit": 0,
    "enable_content_optimization": true,
    "operation_limits": {
      "git_diff": 25000,
      "git_log": 15000,
      "git_status": 10000
    }
  }
}
```

#### Programmatic Configuration
```python
from mcp_server_git.config.token_limits import TokenLimitConfigManager, TokenLimitProfile

config_manager = TokenLimitConfigManager()
settings = config_manager.load_configuration(
    profile=TokenLimitProfile.BALANCED,
    llm_token_limit=15000,  # Custom override
    enable_client_detection=True
)
```

### 3. Predefined Profiles

- **Conservative**: 15K tokens, aggressive optimization, warnings enabled
- **Balanced**: 20K tokens, standard optimization and truncation
- **Aggressive**: 30K tokens, minimal optimization, maximum content preservation
- **Development**: 50K tokens, optimizations disabled, caching enabled

## Usage Examples

### Basic Token Estimation
```python
from mcp_server_git.utils.token_management import TokenEstimator, ContentType

estimator = TokenEstimator()
estimate = estimator.estimate_tokens(diff_content, ContentType.DIFF)
print(f"Estimated tokens: {estimate.estimated_tokens}")
print(f"Confidence: {estimate.confidence}")
```

### Client Detection
```python
from mcp_server_git.utils.token_management import ClientDetector

detector = ClientDetector()
client_type = detector.detect_client_type("Claude/1.0 AI Assistant")
# Returns: ClientType.LLM
```

### Content Optimization
```python
from mcp_server_git.utils.content_optimization import ContentOptimizer, ClientType

optimizer = ContentOptimizer()
optimized = optimizer.optimize_for_client(
    "✅ Successfully committed changes! 🚀",
    ClientType.LLM,
    "git_commit"
)
# Returns: "Commit completed"
```

### Intelligent Truncation
```python
from mcp_server_git.utils.token_management import IntelligentTruncationManager

manager = IntelligentTruncationManager()
result = manager.truncate_for_operation(large_diff, "git_diff", 1000)
print(f"Truncated: {result.truncated}")
print(f"Summary: {result.truncation_summary}")
```

## Performance

### Benchmarks
- **Token Estimation**: <5ms for typical git output
- **Content Optimization**: <10ms for standard responses
- **Intelligent Truncation**: <50ms for large content
- **Total Middleware Overhead**: <100ms (configurable limit)

### Caching
- **Response Caching**: Optional caching of processed responses
- **Configuration Caching**: Hot configuration reloads
- **Token Estimate Caching**: Cached estimates for repeated content

## Testing

Run the comprehensive test suite:

```bash
# Unit tests
python -m pytest tests/test_token_management.py -v

# Integration tests
python examples/token_limit_example.py

# Performance tests
python -m pytest tests/test_performance.py -v
```

### Test Coverage
- Token estimation accuracy across content types
- Truncation semantic preservation
- Client detection reliability
- Content optimization effectiveness
- Configuration loading and validation
- Performance and memory usage

## Monitoring & Metrics

The middleware provides comprehensive metrics:

```python
middleware = create_token_limit_middleware()
metrics = middleware.get_metrics()
```

Available metrics:
- `processed_requests`: Total requests processed
- `truncated_responses`: Number of responses truncated
- `truncation_rate`: Percentage of responses requiring truncation
- `total_tokens_saved`: Total tokens saved through optimization
- `avg_processing_time_ms`: Average processing time per request

## Configuration Reference

### Core Settings
| Setting | Default | Description |
|---------|---------|-------------|
| `llm_token_limit` | 20000 | Token limit for LLM clients |
| `human_token_limit` | 0 | Token limit for human clients (0 = unlimited) |
| `unknown_token_limit` | 25000 | Token limit for unknown clients |
| `enable_content_optimization` | true | Enable LLM content optimization |
| `enable_intelligent_truncation` | true | Enable smart truncation |
| `enable_client_detection` | true | Enable automatic client detection |

### Operation Limits
Override token limits for specific git operations:
- `git_diff`: 25000
- `git_log`: 15000
- `git_status`: 10000
- `github_get_pr_files`: 20000

### Content Optimization
- `remove_emojis_for_llm`: Remove emojis for LLM clients
- `simplify_error_messages`: Simplify verbose error messages
- `add_structure_markers`: Add parsing markers (DIFF_START/END)
- `include_content_summaries`: Add content summaries for long responses

## Advanced Usage

### Custom Truncation Strategies
```python
from mcp_server_git.utils.token_management import ContentTruncator

class CustomTruncator(ContentTruncator):
    def truncate(self, content: str, max_tokens: int, estimator: TokenEstimator) -> TruncationResult:
        # Custom truncation logic
        return TruncationResult(...)

# Register custom truncator
manager = IntelligentTruncationManager()
manager.truncators['custom_operation'] = CustomTruncator()
```

### Dynamic Configuration Updates
```python
middleware.update_config(
    llm_token_limit=15000,
    enable_content_optimization=False
)
```

### Client-Specific Handling
```python
# Force specific client type
config.force_client_type = "llm"

# Custom client detection headers
config.client_detection_headers = ["user-agent", "x-client-type", "x-api-client"]
```

## Troubleshooting

### Common Issues

**1. High Processing Time**
- Reduce `max_processing_time_ms`
- Disable `enable_response_caching`
- Use `development` profile for testing

**2. Over-Aggressive Truncation**
- Increase operation-specific limits
- Use `aggressive` or `development` profile
- Disable `add_truncation_warnings`

**3. Client Detection Issues**
- Set `force_client_type` to override detection
- Add custom indicators to `llm_indicators`
- Enable debug logging: `logging.getLogger('mcp_server_git.utils').setLevel(logging.DEBUG)`

### Debug Logging
```python
import logging
logging.getLogger('mcp_server_git.middlewares.token_limit').setLevel(logging.DEBUG)
logging.getLogger('mcp_server_git.utils.token_management').setLevel(logging.DEBUG)
```

### Performance Profiling
```python
middleware = create_token_limit_middleware()
# ... process requests ...
metrics = middleware.get_metrics()
print(f"Average processing time: {metrics['avg_processing_time_ms']:.2f}ms")
```

## Contributing

### Development Setup
1. Install dependencies: `pixi install`
2. Run tests: `pixi run test`
3. Run linting: `pixi run lint`
4. Run type checking: `pixi run typecheck`

### Adding New Operation Support
1. Create custom truncator in `utils/token_management.py`
2. Register in `IntelligentTruncationManager.truncators`
3. Add operation-specific optimization in `utils/content_optimization.py`
4. Add tests in `tests/test_token_management.py`

## License

This Token Limit Protection System is part of the MCP Git Server project and follows the same licensing terms.

---

## Quick Start Checklist

- [ ] Add `create_enhanced_middleware_chain()` to server initialization
- [ ] Configure token limits via environment variables or config file
- [ ] Test with LLM client to verify optimization
- [ ] Monitor metrics to tune performance
- [ ] Adjust operation-specific limits as needed

The system is designed to work transparently once integrated - LLM clients will automatically receive optimized, token-limited responses while human clients continue to get full formatting.
