#!/usr/bin/env python3
"""
Production Configuration Validation Test

Tests that production validation logic correctly rejects unsafe configurations.
This test runs as a standalone script to avoid pytest's config module caching.
"""

import os
import sys
import importlib
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def reload_config():
    """Force reload of config module"""
    if 'src.utils.config' in sys.modules:
        del sys.modules['src.utils.config']
        del sys.modules['src.utils']
    if 'src' in sys.modules:
        del sys.modules['src']


def test_production_validation_rejects_weak_password():
    """Test that weak passwords are rejected in production"""
    reload_config()
    
    os.environ['APP_ENV'] = 'production'
    os.environ['AUTH_ENABLED'] = 'true'
    os.environ['AUTH_PASSWORD'] = 'weak'  # Too short
    os.environ['AUTH_SECRET_KEY'] = 'SecretKey1234567890abcdefghijklmn'
    os.environ['DEBUG'] = 'false'
    os.environ['SCHEMA_MANAGEMENT'] = 'validate'
    os.environ['CORS_ORIGINS'] = 'https://example.com'
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://user:StrongDBSecret1234567@localhost/db'
    os.environ['JOB_QUEUE_MODE'] = 'background'
    
    from src.utils import config
    
    try:
        config.validate_runtime()
        print("❌ FAIL: Weak password was not rejected")
        return False
    except ValueError as e:
        if 'AUTH_PASSWORD' in str(e):
            print(f"✅ PASS: Weak password rejected")
            return True
        else:
            print(f"❌ FAIL: Wrong error message: {e}")
            return False


def test_production_validation_rejects_weak_secret():
    """Test that weak secret keys are rejected in production"""
    reload_config()
    
    os.environ['APP_ENV'] = 'production'
    os.environ['AUTH_ENABLED'] = 'true'
    os.environ['AUTH_PASSWORD'] = 'StrongAuthKey123456789abc'
    os.environ['AUTH_SECRET_KEY'] = 'short'  # Too short
    os.environ['DEBUG'] = 'false'
    os.environ['SCHEMA_MANAGEMENT'] = 'validate'
    os.environ['CORS_ORIGINS'] = 'https://example.com'
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://user:AnotherStrongDBPass123@localhost/db'
    os.environ['JOB_QUEUE_MODE'] = 'background'
    
    from src.utils import config
    
    try:
        config.validate_runtime()
        print("❌ FAIL: Weak secret key was not rejected")
        return False
    except ValueError as e:
        if 'AUTH_SECRET_KEY' in str(e):
            print(f"✅ PASS: Weak secret key rejected")
            return True
        else:
            print(f"❌ FAIL: Wrong error message: {e}")
            return False


def test_production_validation_rejects_example_values():
    """Test that example-like values are rejected in production"""
    reload_config()
    
    os.environ['APP_ENV'] = 'production'
    os.environ['AUTH_ENABLED'] = 'true'
    os.environ['AUTH_PASSWORD'] = 'CHANGE_ME_secret12345'  # Contains unsafe marker
    os.environ['AUTH_SECRET_KEY'] = 'DifferentSecretKey789012345abcdef'
    os.environ['DEBUG'] = 'false'
    os.environ['SCHEMA_MANAGEMENT'] = 'validate'
    os.environ['CORS_ORIGINS'] = 'https://example.com'
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://user:YetAnotherDBPass567890@localhost/db'
    os.environ['JOB_QUEUE_MODE'] = 'background'
    
    from src.utils import config
    
    try:
        config.validate_runtime()
        print("❌ FAIL: Example-like password was not rejected")
        return False
    except ValueError as e:
        if 'AUTH_PASSWORD' in str(e) and 'high-entropy' in str(e):
            print(f"✅ PASS: Example-like value rejected")
            return True
        else:
            print(f"❌ FAIL: Wrong error message: {e}")
            return False


def test_production_validation_rejects_debug_mode():
    """Test that DEBUG=true is rejected in production"""
    reload_config()
    
    os.environ['APP_ENV'] = 'production'
    os.environ['AUTH_ENABLED'] = 'true'
    os.environ['AUTH_PASSWORD'] = 'ProductionAuthKey123456'
    os.environ['AUTH_SECRET_KEY'] = 'ProductionSecret789012345678abcd'
    os.environ['DEBUG'] = 'true'  # Should be rejected
    os.environ['SCHEMA_MANAGEMENT'] = 'validate'
    os.environ['CORS_ORIGINS'] = 'https://example.com'
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://user:DBPassword567890123456@localhost/db'
    os.environ['JOB_QUEUE_MODE'] = 'background'
    
    from src.utils import config
    
    try:
        config.validate_runtime()
        print("❌ FAIL: DEBUG=true was not rejected")
        return False
    except ValueError as e:
        if 'DEBUG' in str(e) and 'production' in str(e):
            print(f"✅ PASS: DEBUG=true rejected")
            return True
        else:
            print(f"❌ FAIL: Wrong error message: {e}")
            return False


def test_production_validation_rejects_http_cors():
    """Test that HTTP CORS origins are rejected in production"""
    reload_config()
    
    os.environ['APP_ENV'] = 'production'
    os.environ['AUTH_ENABLED'] = 'true'
    os.environ['AUTH_PASSWORD'] = 'SecureAuthKey1234567890abc'
    os.environ['AUTH_SECRET_KEY'] = 'ValidSecretKey1234567890abcdefghij'  # 34 chars, strong enough
    os.environ['DEBUG'] = 'false'
    os.environ['SCHEMA_MANAGEMENT'] = 'validate'
    os.environ['CORS_ORIGINS'] = 'http://insecure.com'  # HTTP should be rejected
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://user:SecureDBAccess123456789xyz@localhost/db'
    os.environ['JOB_QUEUE_MODE'] = 'background'
    
    from src.utils import config
    
    try:
        config.validate_runtime()
        print("❌ FAIL: HTTP CORS origin was not rejected")
        return False
    except ValueError as e:
        error_str = str(e).lower()
        if 'cors' in error_str and 'https' in error_str:
            print(f"✅ PASS: HTTP CORS rejected")
            return True
        else:
            print(f"❌ FAIL: Wrong error message: {e}")
            return False


def test_production_validation_accepts_valid_config():
    """Test that a valid production configuration is accepted"""
    reload_config()
    
    os.environ['APP_ENV'] = 'production'
    os.environ['AUTH_ENABLED'] = 'true'
    os.environ['AUTH_PASSWORD'] = 'ValidProductionKey123456abc'
    os.environ['AUTH_SECRET_KEY'] = 'ValidSecretKey1234567890abcdefghij'  # 34 chars
    os.environ['DEBUG'] = 'false'
    os.environ['SCHEMA_MANAGEMENT'] = 'validate'
    os.environ['CORS_ORIGINS'] = 'https://secure.example.com'
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://user:SecureDBAccess123456789xyz@localhost/db'
    os.environ['JOB_QUEUE_MODE'] = 'background'
    
    from src.utils import config
    
    try:
        config.validate_runtime()
        print("✅ PASS: Valid config accepted")
        return True
    except ValueError as e:
        print(f"❌ FAIL: Valid config rejected: {e}")
        return False


def test_development_allows_weak_config():
    """Test that development mode allows weak configuration"""
    reload_config()
    
    os.environ['APP_ENV'] = 'development'
    os.environ['AUTH_ENABLED'] = 'true'
    os.environ['AUTH_PASSWORD'] = 'dev'  # Weak, but OK in dev
    os.environ['AUTH_SECRET_KEY'] = 'dev'  # Weak, but OK in dev
    os.environ['DEBUG'] = 'true'  # OK in dev
    os.environ['SCHEMA_MANAGEMENT'] = 'create'  # Valid value
    os.environ['CORS_ORIGINS'] = 'http://localhost:3000'  # HTTP OK in dev
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://user:dev@localhost/db'
    os.environ['JOB_QUEUE_MODE'] = 'inline'
    
    from src.utils import config
    
    try:
        config.validate_runtime()
        print("✅ PASS: Weak config allowed in development")
        return True
    except ValueError as e:
        print(f"❌ FAIL: Development config rejected: {e}")
        return False


def main():
    print("Production Configuration Validation Tests")
    print("=" * 70)
    print()
    
    tests = [
        ("Reject weak password", test_production_validation_rejects_weak_password),
        ("Reject weak secret key", test_production_validation_rejects_weak_secret),
        ("Reject example-like values", test_production_validation_rejects_example_values),
        ("Reject DEBUG=true", test_production_validation_rejects_debug_mode),
        ("Reject HTTP CORS", test_production_validation_rejects_http_cors),
        ("Accept valid config", test_production_validation_accepts_valid_config),
        ("Allow weak config in dev", test_development_allows_weak_config),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n{name}:")
        print("-" * 70)
        result = test_func()
        results.append(result)
    
    print()
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All production validation tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
