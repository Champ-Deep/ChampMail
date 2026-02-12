#!/usr/bin/env python3
"""
Champion's Email Engine - Infrastructure Test Script
Run this to verify FalkorDB and Redis are properly configured.

Usage:
    pip install falkordb redis
    python test_infrastructure.py
"""

import sys
from datetime import datetime


def test_falkordb():
    """Test FalkorDB connection and basic graph operations."""
    print("\n=== Testing FalkorDB ===")

    try:
        from falkordb import FalkorDB
    except ImportError:
        print("ERROR: falkordb not installed. Run: pip install falkordb")
        return False

    try:
        # Connect to FalkorDB
        db = FalkorDB(host='localhost', port=6379)
        graph = db.select_graph('champions_test')
        print("Connected to FalkorDB on localhost:6379")

        # Create test nodes (matching PRD schema)
        print("Creating test Prospect and Company nodes...")

        graph.query("""
            CREATE (p:Prospect {
                email: 'test@example.com',
                first_name: 'Test',
                last_name: 'User',
                title: 'VP of Sales',
                created_at: $created_at
            })
        """, {'created_at': datetime.now().isoformat()})

        graph.query("""
            CREATE (c:Company {
                name: 'Test Corp',
                domain: 'example.com',
                industry: 'Technology',
                employee_count: 500
            })
        """)

        # Create relationship
        graph.query("""
            MATCH (p:Prospect {email: 'test@example.com'})
            MATCH (c:Company {domain: 'example.com'})
            CREATE (p)-[:WORKS_AT {title: 'VP of Sales', is_current: true}]->(c)
        """)
        print("Created nodes and relationships")

        # Query it back
        result = graph.query("""
            MATCH (p:Prospect)-[r:WORKS_AT]->(c:Company)
            RETURN p.email, p.first_name, p.last_name, r.title, c.name
        """)

        print("Query results:")
        for record in result.result_set:
            print(f"  {record[1]} {record[2]} ({record[0]}) - {record[3]} at {record[4]}")

        # Clean up test data
        graph.query("MATCH (n) DETACH DELETE n")
        print("Cleaned up test data")

        print("FalkorDB test PASSED")
        return True

    except Exception as e:
        print(f"ERROR: FalkorDB test failed - {e}")
        return False


def test_redis():
    """Test Redis cache connection."""
    print("\n=== Testing Redis Cache ===")

    try:
        import redis
    except ImportError:
        print("ERROR: redis not installed. Run: pip install redis")
        return False

    try:
        # Connect to Redis (on port 6380, separate from FalkorDB)
        r = redis.Redis(host='localhost', port=6380, decode_responses=True)
        r.ping()
        print("Connected to Redis on localhost:6380")

        # Test basic operations
        test_key = "champions:test:key"
        test_value = "infrastructure_test_" + datetime.now().isoformat()

        r.set(test_key, test_value, ex=60)  # 60 second expiry
        retrieved = r.get(test_key)

        if retrieved == test_value:
            print(f"Set/Get test passed: {test_key} = {retrieved}")
        else:
            print(f"ERROR: Value mismatch. Expected {test_value}, got {retrieved}")
            return False

        # Clean up
        r.delete(test_key)
        print("Cleaned up test data")

        print("Redis test PASSED")
        return True

    except redis.ConnectionError as e:
        print(f"ERROR: Cannot connect to Redis - {e}")
        print("Make sure Redis is running: docker compose up -d")
        return False
    except Exception as e:
        print(f"ERROR: Redis test failed - {e}")
        return False


def test_graphiti_integration():
    """Test Graphiti SDK integration with FalkorDB."""
    print("\n=== Testing Graphiti Integration ===")

    try:
        from graphiti_core import Graphiti
        from graphiti_core.driver.falkordb_driver import FalkorDBDriver
    except ImportError:
        print("SKIP: graphiti-core[falkordb] not installed")
        print("To enable: pip install 'graphiti-core[falkordb]'")
        return None  # Skip, not fail

    try:
        # Initialize FalkorDB driver
        driver = FalkorDBDriver(
            host='localhost',
            port=6379,
            database='champions_graphiti_test'
        )

        # Initialize Graphiti (requires OpenAI key for embeddings)
        import os
        if not os.environ.get('OPENAI_API_KEY'):
            print("SKIP: OPENAI_API_KEY not set")
            print("Set it to test full Graphiti functionality")
            return None

        graphiti = Graphiti(graph_driver=driver)
        print("Graphiti initialized with FalkorDB driver")

        # Note: Full Graphiti tests would require async operations
        # and would add episodes to the knowledge graph
        print("Graphiti integration test PASSED (basic)")
        return True

    except Exception as e:
        print(f"ERROR: Graphiti test failed - {e}")
        return False


def main():
    """Run all infrastructure tests."""
    print("=" * 60)
    print("Champion's Email Engine - Infrastructure Test")
    print("=" * 60)

    results = {
        'FalkorDB': test_falkordb(),
        'Redis': test_redis(),
        'Graphiti': test_graphiti_integration(),
    }

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    all_passed = True
    for service, result in results.items():
        if result is True:
            status = "PASSED"
        elif result is False:
            status = "FAILED"
            all_passed = False
        else:
            status = "SKIPPED"
        print(f"  {service}: {status}")

    print("=" * 60)

    if all_passed:
        print("\nAll infrastructure tests passed!")
        print("You can proceed to Cycle 2: FastAPI Backend")
        return 0
    else:
        print("\nSome tests failed. Check the errors above.")
        print("Make sure Docker containers are running:")
        print("  docker compose up -d")
        return 1


if __name__ == "__main__":
    sys.exit(main())
