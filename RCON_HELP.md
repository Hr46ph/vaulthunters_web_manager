# VaultHunters RCON Command Reference

## Core Minecraft Commands

### Server Management
- **`/stop`** - Safely shutdown the server
- **`/save-all [flush]`** - Force save all player data and world chunks
- **`/save-off`** - Disable automatic world saving
- **`/save-on`** - Enable automatic world saving
- **`/reload`** - Reload server configuration and data packs
- **`/perf (start|stop)`** - Start/stop performance profiling

### Player Management
- **`/list [uuids]`** - Show online players (optionally with UUIDs)
- **`/kick <targets> [<reason>]`** - Remove player from server
- **`/ban <targets> [<reason>]`** - Permanently ban players
- **`/ban-ip <target> [<reason>]`** - Ban IP addresses
- **`/pardon <targets>`** - Unban players
- **`/pardon-ip <target>`** - Unban IP addresses
- **`/banlist [ips|players]`** - View banned players/IPs
- **`/whitelist (on|off|list|add|remove|reload)`** - Manage server whitelist
- **`/op <targets>`** - Grant operator privileges
- **`/deop <targets>`** - Remove operator privileges
- **`/setidletimeout <minutes>`** - Set idle timeout duration

### World & Environment
- **`/time (set|add|query)`** - Control world time
- **`/weather (clear|rain|thunder)`** - Change weather conditions
- **`/difficulty [peaceful|easy|normal|hard]`** - Set world difficulty
- **`/gamerule <rule> <value>`** - Modify game rules (see VaultHunters section)
- **`/worldborder (add|set|center|damage|get|warning)`** - Manage world border
- **`/seed`** - Display world seed

### Gameplay Commands
- **`/gamemode (survival|creative|adventure|spectator)`** - Change player gamemode
- **`/defaultgamemode (survival|creative|adventure|spectator)`** - Set default gamemode
- **`/give <targets> <item> [<count>]`** - Give items to players
- **`/clear [<targets>]`** - Clear player inventories
- **`/enchant <targets> <enchantment> [<level>]`** - Apply enchantments
- **`/experience (add|set|query)`** - Manage player experience
- **`/effect (clear|give)`** - Apply or remove status effects

### World Manipulation
- **`/setblock <pos> <block> [destroy|keep|replace]`** - Place single blocks
- **`/fill <from> <to> <block> [replace|keep|outline|hollow|destroy]`** - Fill areas with blocks
- **`/clone <begin> <end> <destination> [replace|masked|filtered]`** - Copy world sections
- **`/summon <entity> [<pos>]`** - Spawn entities
- **`/kill [<targets>]`** - Remove entities or players

### Communication
- **`/say <message>`** - Broadcast server message
- **`/msg <targets> <message>`** - Send private messages
- **`/tellraw <targets> <message>`** - Send formatted JSON messages
- **`/me <action>`** - Send action message
- **`/title <targets> (clear|reset|title|subtitle|actionbar|times)`** - Display titles

## VaultHunters Specific Commands

### VaultHunters Core
- **`/sbvh (createSnapshot|restoreFromSnapshot)`** - Create/restore world snapshots
- **VaultHunters Game Rules:**
  - `finalVaultAllowParty` - Allow parties in final vault
  - `vaultAllowKnowledgeBrew` - Enable knowledge brewing
  - `vaultAllowMentoring` - Allow player mentoring
  - `vaultAllowWaypoints` - Enable waypoint system
  - `vaultBoostPenalty` - Vault boost penalty settings
  - `vaultCrystalMode` - Crystal generation mode
  - `vaultExperience` - Vault experience settings
  - `vaultLevelLock` - Level-based restrictions
  - `vaultLoot` - Vault loot generation
  - `vaultMode` - Core vault gameplay mode
  - `vaultPartyExpSharing` - Party experience sharing
  - `vaultTimer` - Vault time limits

### Mod-Specific Commands

#### Applied Energistics 2
- **`/ae2things [recover|getuuid]`** - AE2 troubleshooting tools

#### Mekanism
- **`/mek (chunk|debug|retrogen|radiation|testrules)`** - Mekanism utilities

#### Refined Storage
- **`/refinedstorage (pattern|disk|network)`** - Storage system management

#### CoFH (Thermal)
- **`/cofh (crafting|workbench|enderchest|friend|heal|ignite|invis|invuln|recharge|repair|zap)`** - Thermal mod utilities

#### Simple Backups
- **`/simplebackups (backup|mergeBackups)`** - Create and manage backups

#### Torch Master
- **`/torchmaster [torchdump|entitydump]`** - Lighting and entity analysis

#### Curios
- **`/curios (list|replace|set|add|remove|clear|drop|reset)`** - Manage curio items

#### Flux Networks
- **`/fluxnetworks superadm`** - Network administration

## Advanced Commands

### Data Management
- **`/data (merge|get|remove|modify)`** - Manipulate NBT data
- **`/datapack (enable|disable|list)`** - Manage data packs
- **`/function <name>`** - Execute function files

### Performance & Debug
- **`/debug (start|stop|function)`** - Debug mode controls
- **`/forge (tps|track|entity|generate|dimensions|mods|tags)`** - Forge debugging
- **`/jfr (start|stop)`** - Java Flight Recorder profiling

### Specialized
- **`/execute (run|if|unless|as|at|store|positioned|rotated|facing|align|anchored|in)`** - Complex command execution
- **`/scoreboard (objectives|players)`** - Scoreboard management
- **`/bossbar (add|remove|list|set|get)`** - Custom boss bars
- **`/schedule (function|clear)`** - Schedule function execution

## Usage Tips

1. **Tab Completion** - Use Tab key for command and parameter completion
2. **Target Selectors** - Use `@a` (all), `@p` (nearest), `@r` (random), `@s` (self)
3. **Coordinates** - Use `~` for relative coordinates, `^` for local coordinates
4. **Safety** - Always use `/save-all` before major operations
5. **VaultHunters** - Many vault settings require server restart to take effect

## Common Workflows

### Server Maintenance
```
/save-all flush
/save-off
# Perform maintenance
/save-on
```

### Player Management
```
/list
/gamemode creative PlayerName
/tp PlayerName ~ ~ ~
```

### Backup & Recovery
```
/save-all flush
/simplebackups backup
/sbvh createSnapshot
```
