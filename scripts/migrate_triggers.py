#!/usr/bin/env python3
"""
UniFi Network Rules Trigger Migration Utility (v4.0.0)

This script helps migrate Home Assistant automations from legacy triggers
to the new unified 'unr_changed' trigger system.

For users upgrading from v3.x to v4.0.0, this utility provides several workflows:

1. Direct migration (if you have file access):
   python migrate_triggers.py --scan automations.yaml
   python migrate_triggers.py --migrate automations.yaml --apply

2. Copy workflow (for easier user experience):
   python migrate_triggers.py --copy-migrate automations_download.yaml
   # This creates both backup and migrated versions

3. Individual operations:
   python migrate_triggers.py --scan automations.yaml
   python migrate_triggers.py --migrate automations.yaml --dry-run
   python migrate_triggers.py --migrate automations.yaml --apply
"""

import argparse
import yaml
import sys
import os
from typing import Dict, Any
from datetime import datetime
import shutil
from pathlib import Path


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
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, indent=2, allow_unicode=True, width=1000)
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


def create_migrated_copy(source_path: str, target_dir: str = None) -> tuple[str, str]:
    """Create both backup and migrated copies of the file.
    
    Returns:
        tuple: (backup_path, migrated_path)
    """
    source_file = Path(source_path)
    if target_dir is None:
        target_dir = source_file.parent
    else:
        target_dir = Path(target_dir)
        target_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = source_file.stem
    extension = source_file.suffix
    
    backup_path = target_dir / f"{base_name}_original_{timestamp}{extension}"
    migrated_path = target_dir / f"{base_name}_migrated_{timestamp}{extension}"
    
    try:
        # Create backup copy
        shutil.copy2(source_path, backup_path)
        # Create working copy for migration
        shutil.copy2(source_path, migrated_path)
        return str(backup_path), str(migrated_path)
    except Exception as e:
        print(f"Error creating copies: {e}")
        return None, None


def is_legacy_unifi_trigger(trigger: Dict[str, Any]) -> bool:
    """Check if trigger is a legacy UniFi Network Rules trigger."""
    # YAML format: platform: unifi_network_rules, type: rule_enabled
    if (trigger.get("platform") == "unifi_network_rules" and
        trigger.get("type") in TRIGGER_MIGRATION_MAP):
        return True
    
    # UI format: trigger: unifi_network_rules, type: rule_enabled
    if (trigger.get("trigger") == "unifi_network_rules" and
        trigger.get("type") in TRIGGER_MIGRATION_MAP):
        return True
    
    return False


def migrate_trigger(trigger: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a single legacy trigger to unified format."""
    if not is_legacy_unifi_trigger(trigger):
        return trigger
    
    legacy_type = trigger["type"]
    migration_config = TRIGGER_MIGRATION_MAP[legacy_type]
    
    # Start with the base migration - always output the standard format
    # Check if this was a UI format trigger and convert accordingly
    if trigger.get("trigger") == "unifi_network_rules":
        # UI format: convert to unified trigger format
        new_trigger = {
            "trigger": "unifi_network_rules",
            "type": migration_config["type"]
        }
    else:
        # YAML format: convert to platform format
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


def update_trigger_templates(automation: Dict[str, Any]) -> Dict[str, Any]:
    """Update template references in automation actions and conditions to use new trigger variables."""
    import re
    
    def replace_trigger_vars(text: str) -> str:
        """Replace old trigger variable references with new ones."""
        if not isinstance(text, str):
            return text
            
        # Replace trigger variable references (order matters - more specific first)
        replacements = [
            # Handle specific complex logic first (before basic replacements)
            (r"'connected' if trigger\.event\.trigger_type\s*==\s*'rule_enabled' else 'disconnected'", 
             "'connected' if trigger.change_action == 'enabled' else 'disconnected'"),
            (r"trigger\.event\.trigger_type\s*==\s*'rule_enabled'", 
             "trigger.change_action == 'enabled'"),
            (r"trigger\.event\.trigger_type\s*==\s*'rule_disabled'", 
             "trigger.change_action == 'disabled'"),
            (r"trigger\.event\.trigger_type\.replace\('rule_', ''\)", 
             "trigger.change_action"),
            # Handle basic variable replacements
            (r'trigger\.event\.rule_name', 'trigger.entity_name'),
            (r'trigger\.event\.trigger_type', 'trigger.change_action'),
            (r'trigger\.event\.rule_id', 'trigger.rule_id'),
            (r'trigger\.event\.rule_type', 'trigger.change_type'),
            # Handle any remaining rule_enabled/rule_disabled values
            (r"'rule_enabled'", "'enabled'"),
            (r"'rule_disabled'", "'disabled'"),
        ]
        
        for old_pattern, new_value in replacements:
            text = re.sub(old_pattern, new_value, text)
        
        return text
    
    def recursive_template_update(obj):
        """Recursively update template strings in nested dictionaries and lists."""
        if isinstance(obj, dict):
            return {key: recursive_template_update(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [recursive_template_update(item) for item in obj]
        elif isinstance(obj, str):
            return replace_trigger_vars(obj)
        else:
            return obj
    
    return recursive_template_update(automation)


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
            # Update template references in the automation if triggers were migrated
            migrated_automation = update_trigger_templates(migrated_automation)
        
        migrated_data.append(migrated_automation)
    
    return migrated_data


def print_scan_results(stats: TriggerMigrationStats, file_path: str = None) -> None:
    """Print scan results."""
    print("\n" + "="*70)
    print("UniFi Network Rules v4.0.0 Trigger Migration Scan Results")
    print("="*70)
    if file_path:
        print(f"Scanned file: {file_path}")
    print(f"Total automations: {stats.total_automations}")
    print(f"Automations with legacy triggers: {stats.automations_with_legacy_triggers}")
    print(f"Total legacy triggers found: {stats.legacy_triggers_found}")
    
    if stats.legacy_trigger_types:
        print("\nLegacy trigger types found:")
        for trigger_type, count in stats.legacy_trigger_types.items():
            print(f"  • {trigger_type}: {count}")
    
    if stats.legacy_triggers_found > 0:
        print(f"\n⚠️  Found {stats.legacy_triggers_found} legacy triggers that need migration!")
        print("\n📋 Next steps:")
        print("   1. Run with --migrate --dry-run to preview changes")
        print("   2. Run with --migrate --apply to apply migration")
        print("   3. Or use --copy-migrate for a safer workflow")
    else:
        print("\n✅ No legacy triggers found. Your automations are already up to date!")
        print("\n🎉 You can safely upgrade to UniFi Network Rules v4.0.0!")


def print_migration_results(stats: TriggerMigrationStats, dry_run: bool = False, backup_path: str = None, migrated_path: str = None) -> None:
    """Print migration results."""
    action = "Would migrate" if dry_run else "Migrated"
    
    print("\n" + "="*70)
    print(f"UniFi Network Rules v4.0.0 Migration Results {'(DRY RUN)' if dry_run else ''}")
    print("="*70)
    print(f"Total automations: {stats.total_automations}")
    print(f"Automations modified: {stats.automations_with_legacy_triggers}")
    print(f"{action} legacy triggers: {stats.legacy_triggers_migrated}")
    
    if backup_path:
        print(f"\n📁 Backup created: {backup_path}")
    if migrated_path:
        print(f"📁 Migrated file: {migrated_path}")
    
    if stats.migration_errors:
        print(f"\n❌ Errors during migration: {len(stats.migration_errors)}")
        for error in stats.migration_errors:
            print(f"  • {error}")
    
    if not dry_run and stats.legacy_triggers_migrated > 0:
        print(f"\n✅ Successfully migrated {stats.legacy_triggers_migrated} triggers!")
        print("\n📋 Next steps:")
        print("   1. Review the migrated automations file")
        print("   2. Test the automations in a development environment if possible")
        print("   3. Upload the migrated file to replace your automations.yaml")
        print("   4. Restart Home Assistant")
        print("   5. Verify your automations are working correctly")
    elif dry_run and stats.legacy_triggers_migrated > 0:
        print(f"\n🔍 Preview completed. {stats.legacy_triggers_migrated} triggers would be migrated.")
        print("\n📋 To apply the migration:")
        print("   • Add --apply flag to apply changes")
        print("   • Or use --copy-migrate for a safer workflow")


def copy_and_migrate_workflow(source_path: str, output_dir: str = None) -> bool:
    """Perform copy-and-migrate workflow for user convenience.
    
    This creates backup and migrated copies of the file without modifying the original.
    """
    print(f"\n🔄 Starting copy-and-migrate workflow for: {source_path}")
    
    if not os.path.exists(source_path):
        print(f"❌ Error: Source file {source_path} does not exist")
        return False
    
    # Create copies
    if output_dir is None:
        output_dir = os.path.dirname(source_path) or "."
    
    backup_path, migrated_path = create_migrated_copy(source_path, output_dir)
    if not backup_path or not migrated_path:
        print("❌ Failed to create file copies")
        return False
    
    print(f"📁 Created backup: {backup_path}")
    print(f"📁 Created working copy: {migrated_path}")
    
    # Load and scan the data
    data = load_yaml_file(migrated_path)
    if data is None:
        print("❌ Failed to load automation data")
        return False
    
    # Scan first
    stats = TriggerMigrationStats()
    scan_automations(data, stats)
    
    if stats.legacy_triggers_found == 0:
        print("\n✅ No legacy triggers found in the file!")
        print("🎉 Your automations are already compatible with v4.0.0")
        # Clean up unnecessary files
        try:
            os.remove(backup_path)
            os.remove(migrated_path)
            print("🧹 Cleaned up temporary files")
        except OSError:
            pass
        return True
    
    print(f"\n📊 Found {stats.legacy_triggers_found} legacy triggers to migrate")
    
    # Perform migration
    migration_stats = TriggerMigrationStats()
    migrated_data = migrate_automations(data, migration_stats)
    
    # Save the migrated data
    if save_yaml_file(migrated_path, migrated_data):
        print_migration_results(migration_stats, dry_run=False, backup_path=backup_path, migrated_path=migrated_path)
        
        print("\n" + "="*70)
        print("📁 COPY-MIGRATE WORKFLOW COMPLETED")
        print("="*70)
        print(f"✅ Original file (unchanged): {source_path}")
        print(f"📋 Backup copy: {backup_path}")
        print(f"🔄 Migrated copy: {migrated_path}")
        print("\n📋 To complete the migration:")
        print("   1. Review the migrated file to ensure it looks correct")
        print("   2. Replace your Home Assistant automations.yaml with the migrated version")
        print("   3. Restart Home Assistant")
        return True
    else:
        print("❌ Failed to save migrated file")
        return False


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Migrate UniFi Network Rules legacy triggers to unified format (v4.0.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Workflow Examples:
  # Copy-and-migrate workflow (recommended for most users)
  python migrate_triggers.py --copy-migrate automations.yaml
  
  # Traditional workflow
  python migrate_triggers.py --scan automations.yaml
  python migrate_triggers.py --migrate automations.yaml --dry-run
  python migrate_triggers.py --migrate automations.yaml --apply
  
  # Direct file migration (use with caution)
  python migrate_triggers.py --migrate /config/automations.yaml --apply

Upgrade Instructions:
  1. Download your automations.yaml from Home Assistant
  2. Run: python migrate_triggers.py --copy-migrate automations.yaml
  3. Review the migrated file
  4. Upload the migrated file to replace your automations.yaml
  5. Restart Home Assistant
        """
    )
    
    parser.add_argument("file", nargs="?", help="Path to Home Assistant automations.yaml file")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", action="store_true", help="Scan for legacy triggers without migrating")
    group.add_argument("--migrate", action="store_true", help="Migrate legacy triggers to unified format")
    group.add_argument("--copy-migrate", metavar="FILE", help="Copy-and-migrate workflow: creates backup and migrated copies")
    
    parser.add_argument("--dry-run", action="store_true", help="Preview migration without applying changes")
    parser.add_argument("--apply", action="store_true", help="Apply migration changes (requires --migrate)")
    parser.add_argument("--output-dir", help="Output directory for copy-migrate workflow (default: same as source)")
    
    args = parser.parse_args()
    
    # Handle copy-migrate workflow
    if args.copy_migrate:
        if args.dry_run or args.apply:
            parser.error("--copy-migrate cannot be used with --dry-run or --apply")
        success = copy_and_migrate_workflow(args.copy_migrate, args.output_dir)
        sys.exit(0 if success else 1)
    
    # Validate arguments for traditional workflow
    if not args.file:
        parser.error("file argument is required for --scan and --migrate")
    
    if args.apply and not args.migrate:
        parser.error("--apply requires --migrate")
    
    if args.migrate and not (args.dry_run or args.apply):
        parser.error("--migrate requires either --dry-run or --apply")
    
    if args.output_dir and not args.copy_migrate:
        parser.error("--output-dir can only be used with --copy-migrate")
    
    # Check if file exists
    if not os.path.exists(args.file):
        print(f"❌ Error: File {args.file} does not exist")
        print("\n💡 Tip: Download your automations.yaml from Home Assistant and use --copy-migrate")
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
        print_scan_results(stats, args.file)
    
    elif args.migrate:
        # Migration mode
        backup_path = None
        if args.apply:
            # Create backup before applying changes
            backup_path = create_backup(args.file)
            if backup_path:
                print(f"📁 Created backup: {backup_path}")
            else:
                print("❌ Failed to create backup. Aborting migration.")
                sys.exit(1)
        
        # Perform migration
        migrated_data = migrate_automations(data, stats)
        
        if args.apply:
            # Save migrated data
            if save_yaml_file(args.file, migrated_data):
                print(f"💾 Saved migrated automations to {args.file}")
            else:
                print("❌ Failed to save migrated file")
                sys.exit(1)
        else:
            # Dry run - show what would be migrated
            print("\n🔍 DRY RUN - No changes were made to the file")
        
        print_migration_results(stats, dry_run=args.dry_run, backup_path=backup_path)


if __name__ == "__main__":
    main()
