"""Tests for CronConfig class."""
from fastapi_crons import CronConfig


class TestCronConfig:
    """Test suite for CronConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CronConfig()

        assert config.sqlite_db_path == "cron_state.db"
        assert config.redis_host == "localhost"
        assert config.redis_port == 6379
        assert config.redis_db == 0
        assert config.enable_distributed_locking is False
        assert config.lock_ttl == 300

    def test_config_from_environment(self, monkeypatch):
        """Test configuration from environment variables."""
        monkeypatch.setenv("CRON_SQLITE_DB_PATH", "/tmp/test.db")
        monkeypatch.setenv("CRON_REDIS_HOST", "redis.example.com")
        monkeypatch.setenv("CRON_REDIS_PORT", "6380")
        monkeypatch.setenv("CRON_ENABLE_DISTRIBUTED_LOCKING", "true")
        monkeypatch.setenv("CRON_LOCK_TTL", "600")

        config = CronConfig()

        assert config.sqlite_db_path == "/tmp/test.db"
        assert config.redis_host == "redis.example.com"
        assert config.redis_port == 6380
        assert config.enable_distributed_locking is True
        assert config.lock_ttl == 600

    def test_instance_id_generation(self):
        """Test that instance ID is generated."""
        config = CronConfig()
        assert config.instance_id is not None
        assert len(config.instance_id) > 0

    def test_instance_id_from_environment(self, monkeypatch):
        """Test instance ID from environment variable."""
        monkeypatch.setenv("CRON_INSTANCE_ID", "custom_instance")
        config = CronConfig()
        assert config.instance_id == "custom_instance"

    def test_redis_url_configuration(self, monkeypatch):
        """Test Redis URL configuration."""
        monkeypatch.setenv("CRON_REDIS_URL", "redis://user:pass@redis.example.com:6380/1")
        config = CronConfig()
        assert config.redis_url == "redis://user:pass@redis.example.com:6380/1"

    def test_log_level_configuration(self, monkeypatch):
        """Test log level configuration."""
        monkeypatch.setenv("CRON_LOG_LEVEL", "DEBUG")
        config = CronConfig()
        assert config.log_level == "DEBUG"

    def test_job_logging_enabled(self, monkeypatch):
        """Test job logging configuration."""
        monkeypatch.setenv("CRON_ENABLE_JOB_LOGGING", "true")
        config = CronConfig()
        assert config.enable_job_logging is True

    def test_job_logging_disabled(self, monkeypatch):
        """Test job logging disabled."""
        monkeypatch.setenv("CRON_ENABLE_JOB_LOGGING", "false")
        config = CronConfig()
        assert config.enable_job_logging is False
