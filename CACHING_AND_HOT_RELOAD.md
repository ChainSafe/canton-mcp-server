# Canonical Resource Caching & Hot-Reload

## Overview

The `DirectFileResourceLoader` now supports:
- ✅ **Disk caching** with commit-hash-based invalidation
- ✅ **Hot-reload** for automatic updates on `git pull`
- ✅ **Fast startup** (~100ms from cache vs ~30s+ cold scan)
- ✅ **Automatic cache cleanup**

## How It Works

### Disk Caching

1. **First Scan**: 
   - Scans 3 canonical repos (daml, canton, daml-finance)
   - Gets commit hash for each repo
   - Saves scan results to `~/.canton-mcp/resource-cache-{hashes}.json`

2. **Subsequent Starts**:
   - Checks current commit hashes
   - Looks for matching cache file
   - Loads instantly if found (~100ms)
   - Falls back to full scan if cache miss

3. **Cache Invalidation**:
   - Automatic when any repo's commit hash changes
   - Manual: delete `~/.canton-mcp/resource-cache-*.json` files

### Hot-Reload (Development Mode)

When enabled via `CANTON_HOT_RELOAD=true`:
- Watches all 3 canonical repo directories
- Detects file changes (e.g., after `git pull`)
- Checks if commit hashes changed
- Automatically re-scans and updates cache
- **Debounced** to handle multi-file git pulls efficiently (2 second delay)

## Usage

### Basic (with caching, no hot-reload)

```bash
# First run - slow (full scan)
uv run canton-mcp-server

# Subsequent runs - FAST (from cache)
uv run canton-mcp-server
```

### Development Mode (with hot-reload)

```bash
# Enable hot-reload
export CANTON_HOT_RELOAD=true
uv run canton-mcp-server

# In another terminal, update a repo
cd /Users/martinmaurer/Projects/Martin/canonical-daml-docs/daml
git pull

# Server automatically detects change and reloads!
```

### Expected Logs

**First Run (Cold Start):**
```
INFO | Scanning cloned repositories for documentation files...
INFO | Scanning repository: daml
INFO | Found 2145 documentation files in daml
INFO | Scanning repository: canton
INFO | Found 876 documentation files in canton
INFO | Scanning repository: daml-finance
INFO | Found 123 documentation files in daml-finance
INFO | Found 3144 documentation files across all repositories
INFO | 💾 Saved to disk cache: resource-cache-daml-abc12345-canton-def67890-daml-finance-ghi11223.json
```

**Second Run (Warm Start):**
```
INFO | ✅ Loaded from disk cache: resource-cache-daml-abc12345-canton-def67890-daml-finance-ghi11223.json
INFO | Loaded 3144 resources from disk cache
```

**Hot-Reload After Git Pull:**
```
INFO | 🔥 Started hot-reload watcher for canonical repositories
INFO | Canonical repo file changed: /path/to/daml/some-file.md
INFO | 📦 Commit hashes changed: daml(abc12345→xyz98765)
INFO | 🔄 Reloading canonical resources...
INFO | Scanning cloned repositories for documentation files...
INFO | Found 3145 documentation files across all repositories
INFO | 💾 Saved to disk cache: resource-cache-daml-xyz98765-canton-def67890-daml-finance-ghi11223.json
INFO | ✅ Resources reloaded after git pull
```

## Cache Location

Cache files are stored in:
```
~/.canton-mcp/resource-cache-{commit-hashes}.json
```

Example filename:
```
resource-cache-daml-abc12345-canton-def67890-daml-finance-ghi11223.json
```

Old cache files are automatically cleaned up when new ones are created.

## Configuration

### Environment Variables

- `CANONICAL_DOCS_PATH`: Path to canonical docs (default: `/Users/martinmaurer/Projects/Martin/canonical-daml-docs`)
- `CANTON_HOT_RELOAD`: Enable hot-reload watching (default: `false`)

### Example

```bash
export CANONICAL_DOCS_PATH=/path/to/canonical-daml-docs
export CANTON_HOT_RELOAD=true
uv run canton-mcp-server
```

## Testing

Run the test script:

```bash
./test_caching.sh
```

This will:
1. Test cold start (no cache)
2. Verify cache creation
3. Test warm start (with cache)
4. Show hot-reload instructions

## Performance

### Before (No Caching):
- **Every startup**: 30-60 seconds (full scan)
- **After git pull**: Manual server restart required

### After (With Caching):
- **First startup**: 30-60 seconds (full scan + save cache)
- **Subsequent startups**: ~100ms (load from cache)
- **After git pull** (hot-reload enabled): Automatic reload (~30s scan)
- **After git pull** (hot-reload disabled): Next startup detects change, loads new cache

## Architecture

### Files Modified:
1. `src/canton_mcp_server/core/direct_file_loader.py`:
   - Added `CanonicalRepoFileHandler` for hot-reload
   - Added disk caching methods
   - Added commit hash checking
   - Added file watcher management

2. `src/canton_mcp_server/handlers/resource_handler.py`:
   - Integrated `CANTON_HOT_RELOAD` environment variable
   - Pass hot-reload flag to `DirectFileResourceLoader`

### Key Methods:
- `_get_all_commit_hashes()`: Get current commit hashes for all repos
- `_load_from_disk_cache()`: Load cached resources by commit hashes
- `_save_to_disk_cache()`: Save resources with commit hashes
- `_start_file_watcher()`: Start watchdog observer for hot-reload
- `_check_and_reload_on_commit_change()`: Detect git pulls and reload

## Troubleshooting

### Cache not loading?
- Check `~/.canton-mcp/.json` exists
- Verify commit hashes match current repos
- Look for "Cache commit hashes don't match" warning

### Hot-reload not working?
- Ensure `CANTON_HOT_RELOAD=true` is set
- Check logs for "🔥 Started hot-reload watcher"
- Verify file changes are detected (look for "Canonical repo file changed")
- Wait 2 seconds after git pull (debounce delay)

### Cache too large?
- Cache file contains full resource data (~10-20MB for 3k+ files)
- This is normal and necessary for fast loading
- Only one cache file per commit hash combination

### Want to force a rescan?
```bash
# Option 1: Delete cache
rm ~/.canton-mcp/resource-cache-*.json

# Option 2: Pass force_refresh (requires code change)
loader.scan_repositories(force_refresh=True)
```

## Future Enhancements

Potential improvements:
- [ ] Add `--clear-cache` CLI flag
- [ ] Add cache compression (gzip)
- [ ] Add cache statistics/metrics
- [ ] Add incremental scanning (only changed files)
- [ ] Add cache expiration (time-based)

