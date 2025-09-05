"""Large test file to generate substantial diffs for token limit testing.
This file contains extensive content to test token truncation capabilities.
"""

# This file will be modified to create large diffs for testing


class LargeTestModule:
    """Large module with extensive content for token testing."""

    def __init__(self):
        self.data = {
            "configuration": {
                "settings": [f"setting_{i}" for i in range(100)],
                "options": [f"option_{i}" for i in range(100)],
                "parameters": [f"param_{i}" for i in range(100)],
            },
            "metadata": {
                "description": "This is a comprehensive test module with extensive metadata",
                "version": "1.0.0",
                "features": [f"feature_{i}" for i in range(50)],
                "capabilities": [f"capability_{i}" for i in range(50)],
            },
        }

    def generate_large_content(self):
        """Generate large content for testing."""
        content = []
        for i in range(200):
            content.append(
                {
                    "id": i,
                    "name": f"TestItem_{i}",
                    "description": f"This is test item {i} with detailed description and extensive metadata",
                    "properties": {
                        "type": f"type_{i % 10}",
                        "category": f"category_{i % 5}",
                        "tags": [f"tag_{j}" for j in range(i % 10 + 1)],
                        "attributes": {
                            f"attr_{j}": f"value_{i}_{j}" for j in range(i % 5 + 1)
                        },
                    },
                    "operations": [
                        f"operation_{j}_for_item_{i}" for j in range(i % 3 + 1)
                    ],
                    "dependencies": [f"dependency_{j}_of_{i}" for j in range(i % 4)],
                }
            )
        return content

    def process_data_extensively(self):
        """Process data with extensive operations."""
        results = []
        for i in range(100):
            processing_result = {
                "iteration": i,
                "timestamp": f"2024-01-{i % 30 + 1:02d}T{i % 24:02d}:00:00Z",
                "processing_steps": [
                    f"Step {j}: Processing item {i} with operation {j}"
                    for j in range(i % 5 + 1)
                ],
                "intermediate_results": [
                    {
                        "step": j,
                        "output": f"Output {j} for iteration {i}",
                        "metadata": {
                            "duration": f"{j * i % 100}ms",
                            "memory_usage": f"{j * i % 1000}MB",
                            "cpu_usage": f"{j * i % 100}%",
                        },
                    }
                    for j in range(i % 3 + 1)
                ],
                "final_result": {
                    "status": "completed" if i % 10 != 0 else "failed",
                    "value": i * 42,
                    "summary": f"Processing completed for iteration {i} with value {i * 42}",
                },
            }
            results.append(processing_result)
        return results


# Generate extensive test data
test_data = []
for category in range(20):
    category_data = {
        "category_id": category,
        "category_name": f"TestCategory_{category}",
        "description": f"This is test category {category} with comprehensive data and extensive documentation",
        "items": [],
    }

    for item in range(50):
        item_data = {
            "item_id": item,
            "item_name": f"Item_{category}_{item}",
            "details": {
                "specification": f"Specification for item {item} in category {category}",
                "requirements": [
                    f"Requirement {req} for item {item}" for req in range(item % 5 + 1)
                ],
                "implementation_notes": [
                    f"Note {note}: Implementation detail {note} for item {item}"
                    for note in range(item % 3 + 1)
                ],
                "test_cases": [
                    {
                        "test_id": f"test_{item}_{test}",
                        "description": f"Test case {test} for item {item}",
                        "steps": [
                            f"Step {step}: Test step {step} for test {test}"
                            for step in range(test % 4 + 1)
                        ],
                        "expected_result": f"Expected result for test {test} of item {item}",
                    }
                    for test in range(item % 3 + 1)
                ],
            },
        }
        category_data["items"].append(item_data)

    test_data.append(category_data)

# Configuration for extensive testing
CONFIGURATION = {
    "database": {
        "hosts": [f"db{i}.example.com" for i in range(10)],
        "credentials": {
            "username": "test_user",
            "password_file": "/secure/passwords/db.txt",
            "ssl_config": {
                "enabled": True,
                "cert_file": "/secure/certs/db.crt",
                "key_file": "/secure/keys/db.key",
            },
        },
        "connection_pools": [
            {
                "pool_id": i,
                "max_connections": 100 + i * 10,
                "timeout": 30 + i,
                "retry_count": 3 + i % 3,
            }
            for i in range(5)
        ],
    },
    "api_endpoints": {
        "base_url": "https://api.example.com",
        "endpoints": [
            {
                "path": f"/api/v1/endpoint_{i}",
                "methods": ["GET", "POST", "PUT", "DELETE"][: (i % 4) + 1],
                "parameters": [f"param_{j}" for j in range(i % 5 + 1)],
                "response_format": f"format_{i % 3}",
            }
            for i in range(25)
        ],
    },
    "monitoring": {
        "metrics": [
            {
                "name": f"metric_{i}",
                "description": f"Monitoring metric {i} for system performance",
                "unit": ["seconds", "bytes", "count", "percentage"][i % 4],
                "threshold": {
                    "warning": i * 10,
                    "critical": i * 20,
                    "alert_channels": [f"channel_{j}" for j in range(i % 3 + 1)],
                },
            }
            for i in range(30)
        ]
    },
}


def get_small_test_data():
    """Generate small test data for middleware testing."""
    return {
        "operation": "get_file",
        "content": "Small test content " * 10,  # ~200 chars
        "metadata": {"type": "small", "size": "small"},
    }


def get_medium_test_data():
    """Generate medium test data for middleware testing."""
    content = []
    for i in range(100):
        content.append(
            f"Medium test content line {i} with additional data and metadata"
        )
    return {
        "operation": "get_diff",
        "content": "\n".join(content),  # ~5-6K chars
        "metadata": {"type": "medium", "size": "medium"},
    }


def get_large_test_data():
    """Generate large test data for middleware testing."""
    content = []
    for i in range(500):
        content.append(
            f"Large test content line {i} with extensive data, metadata, and verbose logging information that creates substantial token overhead"
        )
    return {
        "operation": "get_log",
        "content": "\n".join(content),  # ~50K+ chars
        "metadata": {"type": "large", "size": "large"},
    }


def main() -> None:
    """Main function with extensive processing."""
    module = LargeTestModule()

    print("Starting extensive processing...")
    large_content = module.generate_large_content()
    print(f"Generated {len(large_content)} items")

    processing_results = module.process_data_extensively()
    print(f"Processed {len(processing_results)} iterations")

    print("Configuration loaded with:")
    print(f"- Database hosts: {len(CONFIGURATION['database']['hosts'])}")
    print(f"- API endpoints: {len(CONFIGURATION['api_endpoints']['endpoints'])}")
    print(f"- Monitoring metrics: {len(CONFIGURATION['monitoring']['metrics'])}")

    print("Processing complete!")


# Additional extensive content for testing large diffs
ADDITIONAL_TEST_DATA = {
    "performance_benchmarks": [
        {
            "benchmark_id": i,
            "name": f"Benchmark_{i}",
            "description": f"Performance benchmark {i} testing system capabilities under load",
            "test_scenarios": [
                {
                    "scenario_id": j,
                    "name": f"Scenario_{i}_{j}",
                    "description": f"Test scenario {j} for benchmark {i}",
                    "parameters": {
                        "load_level": j * 10,
                        "duration": f"{j * 5}minutes",
                        "concurrent_users": j * 100,
                        "data_size": f"{j * 1000}MB",
                    },
                    "expected_results": {
                        "response_time": f"< {j * 100}ms",
                        "throughput": f"> {j * 50} ops/sec",
                        "error_rate": f"< {j * 0.1}%",
                        "resource_usage": {
                            "cpu": f"< {j * 20}%",
                            "memory": f"< {j * 100}MB",
                            "disk_io": f"< {j * 10}MB/s",
                        },
                    },
                }
                for j in range(i % 8 + 1)
            ],
            "baseline_metrics": {
                "cpu_usage": f"{i * 5}%",
                "memory_usage": f"{i * 20}MB",
                "disk_usage": f"{i * 100}MB",
                "network_usage": f"{i * 10}KB/s",
            },
        }
        for i in range(50)
    ],
    "integration_tests": [
        {
            "test_suite_id": i,
            "name": f"IntegrationSuite_{i}",
            "description": f"Integration test suite {i} for comprehensive system testing",
            "test_cases": [
                {
                    "case_id": f"case_{i}_{j}",
                    "name": f"TestCase_{i}_{j}",
                    "description": f"Integration test case {j} in suite {i}",
                    "setup_steps": [
                        f"Setup step {step}: {step} preparation for test case {j}"
                        for step in range(j % 5 + 1)
                    ],
                    "execution_steps": [
                        f"Execute step {step}: {step} execution for test case {j}"
                        for step in range(j % 6 + 1)
                    ],
                    "verification_steps": [
                        f"Verify step {step}: {step} verification for test case {j}"
                        for step in range(j % 4 + 1)
                    ],
                    "cleanup_steps": [
                        f"Cleanup step {step}: {step} cleanup for test case {j}"
                        for step in range(j % 3 + 1)
                    ],
                }
                for j in range(i % 10 + 1)
            ],
        }
        for i in range(30)
    ],
}

# Massive configuration object for testing
MASSIVE_CONFIG = {
    "microservices": [
        {
            "service_id": i,
            "name": f"microservice_{i}",
            "description": f"Microservice {i} providing specialized functionality",
            "endpoints": [
                {
                    "endpoint_id": f"endpoint_{i}_{j}",
                    "path": f"/api/v1/service_{i}/endpoint_{j}",
                    "method": ["GET", "POST", "PUT", "DELETE", "PATCH"][j % 5],
                    "description": f"Endpoint {j} for microservice {i}",
                    "parameters": [
                        {
                            "name": f"param_{k}",
                            "type": ["string", "integer", "boolean", "object"][k % 4],
                            "required": k % 2 == 0,
                            "description": f"Parameter {k} for endpoint {j}",
                        }
                        for k in range(j % 8 + 1)
                    ],
                    "responses": [
                        {
                            "status_code": [200, 400, 401, 403, 404, 500][k % 6],
                            "description": f"Response {k} for endpoint {j}",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    f"field_{field_idx}": {
                                        "type": ["string", "number", "boolean"][
                                            field_idx % 3
                                        ],
                                        "description": f"Field {field_idx} in response {k}",
                                    }
                                    for field_idx in range(k % 5 + 1)
                                },
                            },
                        }
                        for k in range(j % 4 + 1)
                    ],
                }
                for j in range(i % 12 + 1)
            ],
            "dependencies": [
                {
                    "service_name": f"dependency_{i}_{k}",
                    "type": ["database", "cache", "queue", "external_api"][k % 4],
                    "configuration": {
                        "host": f"host_{k}.example.com",
                        "port": 8000 + k,
                        "timeout": 30 + k,
                        "retry_count": 3 + k % 3,
                    },
                }
                for k in range(i % 6 + 1)
            ],
        }
        for i in range(25)
    ]
}

if __name__ == "__main__":
    main()

    # Additional processing for extended testing
    print("\nProcessing additional test data...")
    print(
        f"Performance benchmarks: {len(ADDITIONAL_TEST_DATA['performance_benchmarks'])}"
    )
    print(f"Integration test suites: {len(ADDITIONAL_TEST_DATA['integration_tests'])}")
    print(f"Microservices configured: {len(MASSIVE_CONFIG['microservices'])}")

    total_endpoints = sum(
        len(service["endpoints"]) for service in MASSIVE_CONFIG["microservices"]
    )
    print(f"Total API endpoints: {total_endpoints}")

    print("Extended processing complete!")
