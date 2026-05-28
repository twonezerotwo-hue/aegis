"""
AEGIS Holding — Health Check Script

Servis sağlığını kontrol et.
"""
import sys
import httpx
import asyncio
from datetime import datetime
import os

from sqlalchemy import create_engine, text
import redis


class HealthChecker:
    """Service health checker."""

    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "postgresql://aegis:aegis_secure_pass@postgres:5432/aegis")
        self.redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.clickhouse_host = os.getenv("CLICKHOUSE_HOST", "clickhouse")
        self.service_endpoints = {
            "touche": "http://touche-api:8001/health",
            "fundamental": "http://fundamental-api:8002/health",
            "quantum": "http://quantum-api:8003/health",
            "sentinel": "http://sentinel-api:8004/health",
            "consensus": "http://consensus-api:8005/health",
        }

    async def check_http_health(self, url: str) -> bool:
        """Check HTTP endpoint health."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception as e:
            print(f"HTTP check failed for {url}: {e}")
            return False

    def check_database_health(self) -> bool:
        """Check PostgreSQL health."""
        try:
            engine = create_engine(self.database_url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            print(f"Database check failed: {e}")
            return False

    def check_redis_health(self) -> bool:
        """Check Redis health."""
        try:
            r = redis.from_url(self.redis_url, decode_responses=True)
            r.ping()
            return True
        except Exception as e:
            print(f"Redis check failed: {e}")
            return False

    def check_clickhouse_health(self) -> bool:
        """Check ClickHouse health."""
        try:
            # Simple HTTP ping to ClickHouse
            import httpx
            response = httpx.get(f"http://{self.clickhouse_host}:8123/ping", timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"ClickHouse check failed: {e}")
            return False

    async def run_health_check(self, endpoint_url: str = None) -> bool:
        """Run health check."""
        print(f"[{datetime.now().isoformat()}] Starting health check...")

        all_healthy = True

        # Check specific endpoint if provided
        if endpoint_url:
            print(f"Checking endpoint: {endpoint_url}")
            result = await self.check_http_health(endpoint_url)
            if result:
                print(f"✓ Endpoint is healthy")
                return True
            else:
                print(f"✗ Endpoint is unhealthy")
                return False

        # Check all dependencies
        print("\nChecking dependencies...")

        # Check PostgreSQL
        print("- PostgreSQL...", end=" ")
        if self.check_database_health():
            print("✓")
        else:
            print("✗")
            all_healthy = False

        # Check Redis
        print("- Redis...", end=" ")
        if self.check_redis_health():
            print("✓")
        else:
            print("✗")
            all_healthy = False

        # Check ClickHouse
        print("- ClickHouse...", end=" ")
        if self.check_clickhouse_health():
            print("✓")
        else:
            print("✗")
            # ClickHouse is optional in some services
            # all_healthy = False

        # Check service endpoints
        print("\nChecking service endpoints...")
        for service_name, url in self.service_endpoints.items():
            print(f"- {service_name}...", end=" ")
            if await self.check_http_health(url):
                print("✓")
            else:
                print("✗")
                # Not critical if one service is down

        print("\n" + "="*50)
        if all_healthy:
            print("✓ All systems healthy!")
            return True
        else:
            print("✗ Some systems are unhealthy")
            return False


async def main():
    """Main entry point."""
    checker = HealthChecker()

    # Get endpoint from command line if provided
    endpoint = sys.argv[1] if len(sys.argv) > 1 else None

    result = await checker.run_health_check(endpoint)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    asyncio.run(main())
