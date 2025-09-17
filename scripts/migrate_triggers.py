#!/usr/bin/env python3
"""
UniFi Network Rules Trigger Migration Utility

This script helps migrate Home Assistant automations from legacy triggers
to the new unified 'unr_changed' trigger system.

Usage:
    python scripts/migrate_triggers.py --scan /config/automations.yaml
    python scripts/migrate_triggers.py --migrate /config/automations.yaml --dry-run
    python scripts/migrate_triggers.py --migrate /config/automations.yaml --apply
"""

import argparse
import yaml
import sys
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import shutil


# Legacy to unified trigger mapping
TRIGGER_MIGRATION_MAP = {
    "rule_enabled": {
        "type": "unr_changed",
        "change_action": "enabled"
    },
    "rule_disabled": {
        "type": "unr_changed", 
        "change_action": "disabled"
    },
    "rule_changed": {
        "type": "unr_changed",
        "change_action": ["enabled", "disabled", "modified"]
    },
    "rule_deleted": {
        "type": "unr_changed",
        "change_action": "deleted"
    },
    "device_changed": {
        "type": "unr_changed",
        "change_type": "device"
    }
}

# Legacy rule type to new change type mapping
RULE_TYPE_MIGRATION_MAP = {
    "firewall_policies": "firewall_policy",
    "traffic_routes": "traffic_route",
    "port_forwards": "port_forward", 
    "traffic_rules": "traffic_rule",
    "legacy_firewall_rules": "firewall_policy",
    "firewall_zones": "firewall_zone",
    "wlans": "wlan",
    "qos_rules": "qos_rule",
    "vpn_clients": "vpn_client",
    "vpn_servers": "vpn_server"
}


class TriggerMigrationStats:
    """Statistics tracking for migration."""
    
    def __init__(self):
        self.total_automations = 0
        self.automations_with_legacy_triggers = 0
        self.legacy_triggers_found = 0
        self.legacy_triggers_migrated = 0
        self.migration_errors = []
        self.legacy_trigger_types = {}


def load_yaml_file(file_path: str) -> Any:
    """Load YAML file safely."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading YAML file {file_path}: {e}")
        return None


def save_yaml_file(file_path: str, data: Any) -> bool:
    """Save YAML file safely."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving YAML file {file_path}: {e}")
        return False


def create_backup(file_path: str) -> str:
    """Create a backup of the file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.backup_{timestamp}"
    try:
        shutil.copy2(file_path, backup_path)
        return backup_path
    except Exception as e:
        print(f"Error creating backup: {e}")
        return None


def is_legacy_unifi_trigger(trigger: Dict[str, Any]) -> bool:
    """Check if trigger is a legacy UniFi Network Rules trigger."""
    return (
        trigger.get("platform") == "unifi_network_rules" and
        trigger.get("type") in TRIGGER_MIGRATION_MAP
    )


def migrate_trigger(trigger: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a single legacy trigger to unified format."""
    if not is_legacy_unifi_trigger(trigger):
        return trigger
    
    legacy_type = trigger["type"]
    migration_config = TRIGGER_MIGRATION_MAP[legacy_type]
    
    # Start with the base migration
    new_trigger = {
        "platform": "unifi_network_rules",
        "type": migration_config["type"]
    }
    
    # Add change_action if specified
    if "change_action" in migration_config:
        new_trigger["change_action"] = migration_config["change_action"]
    
    # Add change_type if specified  
    if "change_type" in migration_config:
        new_trigger["change_type"] = migration_config["change_type"]
    
    # Migrate legacy rule_type to change_type
    if "rule_type" in trigger and "change_type" not in new_trigger:
        legacy_rule_type = trigger["rule_type"]
        if legacy_rule_type in RULE_TYPE_MIGRATION_MAP:
            new_trigger["change_type"] = RULE_TYPE_MIGRATION_MAP[legacy_rule_type]
    
    # Copy over other compatible fields
    for field in ["entity_id", "name_filter"]:
        if field in trigger:
            new_trigger[field] = trigger[field]
    
    # Handle special cases
    if legacy_type == "device_changed":
        # For device triggers, we need to convert device_id and change_type
        if "device_id" in trigger:
            # Convert device_id to entity_id format
            device_id = trigger["device_id"].replace(":", "").lower()
            new_trigger["entity_id"] = f"switch.unr_device_{device_id}_led"
        
        if "change_type" in trigger and trigger["change_type"] == "led_toggled":
            new_trigger["change_action"] = ["enabled", "disabled"]
    
    return new_trigger


def scan_automations(data: Any, stats: TriggerMigrationStats) -> None:
    """Scan automations for legacy triggers."""
    if not isinstance(data, list):
        return
    
    for automation in data:
        if not isinstance(automation, dict):
            continue
            
        stats.total_automations += 1
        automation_has_legacy = False
        
        # Check single trigger
        if "trigger" in automation:
            trigger = automation["trigger"]
            if isinstance(trigger, dict) and is_legacy_unifi_trigger(trigger):
                automation_has_legacy = True
                stats.legacy_triggers_found += 1
                trigger_type = trigger.get("type")
                stats.legacy_trigger_types[trigger_type] = stats.legacy_trigger_types.get(trigger_type, 0) + 1
        
        # Check multiple triggers
        elif "triggers" in automation:
            triggers = automation["triggers"]
            if isinstance(triggers, list):
                for trigger in triggers:
                    if isinstance(trigger, dict) and is_legacy_unifi_trigger(trigger):
                        automation_has_legacy = True
                        stats.legacy_triggers_found += 1
                        trigger_type = trigger.get("type")
                        stats.legacy_trigger_types[trigger_type] = stats.legacy_trigger_types.get(trigger_type, 0) + 1
        
        if automation_has_legacy:
            stats.automations_with_legacy_triggers += 1


def migrate_automations(data: Any, stats: TriggerMigrationStats) -> Any:
    """Migrate all automations in the data."""
    if not isinstance(data, list):
        return data
    
    migrated_data = []
    
    for automation in data:
        if not isinstance(automation, dict):
            migrated_data.append(automation)
            continue
        
        stats.total_automations += 1
        migrated_automation = automation.copy()
        automation_changed = False
        
        # Migrate single trigger
        if "trigger" in migrated_automation:
            trigger = migrated_automation["trigger"]
            if isinstance(trigger, dict) and is_legacy_unifi_trigger(trigger):
                migrated_trigger = migrate_trigger(trigger)
                migrated_automation["trigger"] = migrated_trigger
                automation_changed = True
                stats.legacy_triggers_migrated += 1
        
        # Migrate multiple triggers
        elif "triggers" in migrated_automation:
            triggers = migrated_automation["triggers"]
            if isinstance(triggers, list):
                migrated_triggers = []
                for trigger in triggers:
                    if isinstance(trigger, dict) and is_legacy_unifi_trigger(trigger):
                        migrated_trigger = migrate_trigger(trigger)
                        migrated_triggers.append(migrated_trigger)
                        automation_changed = True
                        stats.legacy_triggers_migrated += 1
                    else:
                        migrated_triggers.append(trigger)
                migrated_automation["triggers"] = migrated_triggers
        
        if automation_changed:
            stats.automations_with_legacy_triggers += 1
        
        migrated_data.append(migrated_automation)
    
    return migrated_data


def print_scan_results(stats: TriggerMigrationStats) -> None:
    """Print scan results."""
    print("\n" + "="*60)
    print("UniFi Network Rules Trigger Migration Scan Results")
    print("="*60)
    print(f"Total automations: {stats.total_automations}")
    print(f"Automations with legacy triggers: {stats.automations_with_legacy_triggers}")
    print(f"Total legacy triggers found: {stats.legacy_triggers_found}")
    
    if stats.legacy_trigger_types:
        print("\nLegacy trigger types found:")
        for trigger_type, count in stats.legacy_trigger_types.items():
            print(f"  {trigger_type}: {count}")
    
    if stats.legacy_triggers_found > 0:
        print(f"\n⚠️  Found {stats.legacy_triggers_found} legacy triggers that need migration!")
        print("Run with --migrate to migrate them to the new unified format.")
    else:
        print("\n✅ No legacy triggers found. Your automations are already up to date!")


def print_migration_results(stats: TriggerMigrationStats, dry_run: bool = False) -> None:
    """Print migration results."""
    action = "Would migrate" if dry_run else "Migrated"
    
    print("\n" + "="*60)
    print(f"UniFi Network Rules Trigger Migration Results {'(DRY RUN)' if dry_run else ''}")
    print("="*60)
    print(f"Total automations: {stats.total_automations}")
    print(f"Automations modified: {stats.automations_with_legacy_triggers}")
    print(f"{action} legacy triggers: {stats.legacy_triggers_migrated}")
    
    if stats.migration_errors:
        print(f"\n❌ Errors during migration: {len(stats.migration_errors)}")
        for error in stats.migration_errors:
            print(f"  {error}")
    
    if not dry_run and stats.legacy_triggers_migrated > 0:
        print(f"\n✅ Successfully migrated {stats.legacy_triggers_migrated} triggers!")
        print("Please review your automations and test them before restarting Home Assistant.")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Migrate UniFi Network Rules legacy triggers to unified format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan for legacy triggers
  python scripts/migrate_triggers.py --scan /config/automations.yaml
  
  # Preview migration (dry run)
  python scripts/migrate_triggers.py --migrate /config/automations.yaml --dry-run
  
  # Apply migration (creates backup automatically)
  python scripts/migrate_triggers.py --migrate /config/automations.yaml --apply
        """
    )
    
    parser.add_argument("file", help="Path to Home Assistant automations.yaml file")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", action="store_true", help="Scan for legacy triggers without migrating")
    group.add_argument("--migrate", action="store_true", help="Migrate legacy triggers to unified format")
    
    parser.add_argument("--dry-run", action="store_true", help="Preview migration without applying changes")
    parser.add_argument("--apply", action="store_true", help="Apply migration changes (requires --migrate)")
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.apply and not args.migrate:
        parser.error("--apply requires --migrate")
    
    if args.migrate and not (args.dry_run or args.apply):
        parser.error("--migrate requires either --dry-run or --apply")
    
    # Check if file exists
    if not os.path.exists(args.file):
        print(f"Error: File {args.file} does not exist")
        sys.exit(1)
    
    # Load YAML data
    print(f"Loading automations from {args.file}...")
    data = load_yaml_file(args.file)
    if data is None:
        sys.exit(1)
    
    stats = TriggerMigrationStats()
    
    if args.scan:
        # Scan mode
        scan_automations(data, stats)
        print_scan_results(stats)
    
    elif args.migrate:
        # Migration mode
        if args.apply:
            # Create backup before applying changes
            backup_path = create_backup(args.file)
            if backup_path:
                print(f"Created backup: {backup_path}")
            else:
                print("Failed to create backup. Aborting migration.")
                sys.exit(1)
        
        # Perform migration
        migrated_data = migrate_automations(data, stats)
        
        if args.apply:
            # Save migrated data
            if save_yaml_file(args.file, migrated_data):
                print(f"Saved migrated automations to {args.file}")
            else:
                print("Failed to save migrated file")
                sys.exit(1)
        else:
            # Dry run - show what would be migrated
            print("DRY RUN - No changes were made to the file")
        
        print_migration_results(stats, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
