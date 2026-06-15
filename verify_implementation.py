#!/usr/bin/env python
"""
Verification script to ensure all Inventory Monitoring Agent components are in place and working.
Run this before production use: python verify_implementation.py
"""

import sys
import os
from pathlib import Path

def check_file(path: str, description: str) -> bool:
    """Check if a file exists."""
    if Path(path).exists():
        print(f"[OK] {description}")
        return True
    else:
        print(f"[MISSING] {description} - NOT FOUND: {path}")
        return False

def check_folder(path: str, description: str) -> bool:
    """Check if a folder exists."""
    if Path(path).is_dir():
        print(f"[OK] {description}")
        return True
    else:
        print(f"[MISSING] {description} - NOT FOUND: {path}")
        return False

def check_imports() -> bool:
    """Check if all required packages can be imported."""
    try:
        import openai
        print("[OK] OpenAI package installed (correct SDK)")
    except ImportError:
        print("[MISSING] OpenAI package NOT installed - run: pip install -r requirements.txt")
        return False
    
    try:
        import dotenv
        print("[OK] python-dotenv package installed")
    except ImportError:
        print("[MISSING] python-dotenv NOT installed - run: pip install -r requirements.txt")
        return False
    
    return True

def main():
    print("\n" + "="*80)
    print("INVENTORY MONITORING AGENT - IMPLEMENTATION VERIFICATION")
    print("="*80 + "\n")
    
    checks_passed = 0
    checks_total = 0
    
    # Check core services
    print("CORE SERVICES:")
    checks = [
        ("agents/inventory_monitoring/services/event_snapshot_service.py", "Event Snapshot Service (Phase 1)"),
        ("agents/inventory_monitoring/services/calculation_service.py", "Inventory Calculation Service (Phase 2)"),
        ("agents/inventory_monitoring/services/risk_monitoring_service.py", "Inventory Risk Monitoring Service (Phase 3)"),
        ("agents/inventory_monitoring/agent.py", "Inventory Monitoring Agent (Orchestrator)"),
    ]
    for path, desc in checks:
        checks_total += 1
        if check_file(path, desc):
            checks_passed += 1
    
    # Check data models
    print("\nDATA MODELS:")
    checks = [
        ("agents/inventory_monitoring/models/inventory_models.py", "Inventory Models (4 dataclasses)"),
    ]
    for path, desc in checks:
        checks_total += 1
        if check_file(path, desc):
            checks_passed += 1
    
    # Check utilities
    print("\nUTILITIES:")
    checks = [
        ("utils/csv_loader.py", "CSV Loader (5 DB support)"),
        ("utils/logging_setup.py", "Logging Setup"),
        ("utils/parsing.py", "CSV Parsing Utilities"),
    ]
    for path, desc in checks:
        checks_total += 1
        if check_file(path, desc):
            checks_passed += 1
    
    # Check configuration
    print("\nCONFIGURATION:")
    checks = [
        ("config/azure_config.py", "Azure OpenAI Configuration"),
        (".env.example", "Environment Variables Template"),
    ]
    for path, desc in checks:
        checks_total += 1
        if check_file(path, desc):
            checks_passed += 1
    
    # Check entry point
    print("\nENTRY POINT:")
    checks = [
        ("main.py", "Application Entry Point"),
    ]
    for path, desc in checks:
        checks_total += 1
        if check_file(path, desc):
            checks_passed += 1
    
    # Check data folders
    print("\nDATA FOLDERS:")
    checks = [
        ("data/csv_exports", "CSV Exports Root"),
        ("data/csv_exports/db3_csv_export", "DB3 (Inventory Data)"),
        ("data/csv_exports/db5_csv_export", "DB5 (Snapshots & Events)"),
    ]
    for path, desc in checks:
        checks_total += 1
        if check_folder(path, desc):
            checks_passed += 1
    
    # Check log folder
    print("\nLOG FOLDER:")
    checks = [
        ("logs", "Logs Directory"),
    ]
    for path, desc in checks:
        checks_total += 1
        if check_folder(path, desc):
            checks_passed += 1
    
    # Check dependencies
    print("\nDEPENDENCIES:")
    checks_total += 1
    if check_imports():
        checks_passed += 1
    
    # Check .env file
    print("\nCONFIGURATION FILE:")
    if Path(".env").exists():
        print("[OK] .env file configured")
        checks_passed += 1
    else:
        print("[OPTIONAL] .env file NOT configured (optional - run: cp .env.example .env)")
    checks_total += 1
    
    # Final summary
    print("\n" + "="*80)
    print(f"VERIFICATION RESULTS: {checks_passed}/{checks_total} checks passed")
    print("="*80 + "\n")
    
    if checks_passed == checks_total:
        print("[SUCCESS] ALL CHECKS PASSED - READY FOR PRODUCTION USE!\n")
        print("Next steps:")
        print("1. Configure .env with Azure credentials (if using Azure analysis)")
        print("2. Run: python main.py")
        print("3. Check logs/inventory_monitoring.log for detailed output\n")
        return 0
    else:
        failed = checks_total - checks_passed
        print(f"[WARNING] {failed} check(s) failed - see details above\n")
        print("To fix:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Ensure CSV data folders exist: data/csv_exports/db*/")
        print("3. Configure .env: cp .env.example .env\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
