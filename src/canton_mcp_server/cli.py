"""
Canton MCP Server CLI entry point.
"""

import argparse
import sys
import uvicorn
from pathlib import Path
import os

from .server import app
from .core.direct_file_loader import DirectFileResourceLoader
from .core.llm_enrichment import LLMEnrichmentEngine


def main():
    """Main CLI entry point - starts the Canton MCP Server or runs enrichment commands"""
    parser = argparse.ArgumentParser(description="Canton MCP Server")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Server command
    server_parser = subparsers.add_parser("server", help="Start the MCP server")
    
    # Enrich command
    enrich_parser = subparsers.add_parser("enrich", help="Enrich canonical resources with LLM")
    enrich_parser.add_argument(
        "--all",
        action="store_true",
        help="Force re-enrichment of all files (default: only new/changed files)"
    )
    enrich_parser.add_argument(
        "--new",
        action="store_true",
        help="Enrich only new/changed files (default behavior)"
    )
    enrich_parser.add_argument(
        "--status",
        action="store_true",
        help="Show enrichment cache status"
    )
    enrich_parser.add_argument(
        "--stats",
        action="store_true",
        help="Show enrichment statistics"
    )
    
    args = parser.parse_args()
    
    # Default to server if no command specified
    if args.command is None or args.command == "server":
        print("\n" + "─" * 60)
        print("  Canton MCP Server v0.1 | http://localhost:7284/mcp")
        print("  DAML Validation & Authorization Patterns")
        print("─" * 60 + "\n")
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=7284,
            log_level="info",
            timeout_keep_alive=30 * 60,
            timeout_graceful_shutdown=30,
        )
    elif args.command == "enrich":
        handle_enrich_command(args)
    else:
        parser.print_help()
        sys.exit(1)


def handle_enrich_command(args):
    """Handle enrich command."""
    # Check if enrichment is enabled
    if not os.getenv("ENABLE_LLM_ENRICHMENT", "false").lower() == "true":
        print("❌ LLM enrichment is disabled.")
        print("Set ENABLE_LLM_ENRICHMENT=true and ANTHROPIC_API_KEY in your environment.")
        sys.exit(1)
    
    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY not set.")
        print("Set ANTHROPIC_API_KEY in your environment to enable enrichment.")
        sys.exit(1)
    
    # Initialize enrichment engine
    enrichment_engine = LLMEnrichmentEngine()
    
    if not enrichment_engine.enabled:
        print("❌ Enrichment engine not available.")
        sys.exit(1)
    
    # Handle status command
    if args.status:
        status = enrichment_engine.get_cache_status()
        print("\n📊 Enrichment Cache Status")
        print("─" * 60)
        print(f"Enabled: {status['enabled']}")
        print(f"Total Enrichments: {status['total_enrichments']}")
        print(f"Last Updated: {status.get('last_updated', 'Never')}")
        print(f"Cache File: {status['cache_file']}")
        print("\nRepositories:")
        for repo, info in status.get('repos', {}).items():
            print(f"  {repo}: commit={info.get('commit', 'unknown')[:8]}...")
        return
    
    # Handle stats command
    if args.stats:
        stats = enrichment_engine.get_stats()
        print("\n📈 Enrichment Statistics")
        print("─" * 60)
        print(f"Total Enrichments: {stats['total_enrichments']}")
        print("\nUse Case Distribution:")
        for use_case, count in stats.get('use_case_distribution', {}).items():
            print(f"  {use_case}: {count}")
        print("\nSecurity Level Distribution:")
        for level, count in stats.get('security_level_distribution', {}).items():
            print(f"  {level}: {count}")
        print("\nComplexity Level Distribution:")
        for level, count in stats.get('complexity_level_distribution', {}).items():
            print(f"  {level}: {count}")
        return
    
    # Handle enrichment command
    print("\n🔍 Loading canonical resources...")
    
    # Get canonical docs path
    canonical_docs_path = Path(os.environ.get("CANONICAL_DOCS_PATH", "../../canonical-daml-docs"))
    loader = DirectFileResourceLoader(canonical_docs_path)
    
    # Scan repositories
    resources_dict = loader.scan_repositories(force_refresh=False)
    
    # Get all resources as flat list
    all_resources = []
    for resource_list in resources_dict.values():
        all_resources.extend(resource_list)
    
    # Get commit hashes
    commit_hashes = loader._get_all_commit_hashes()
    
    # Determine if forcing all
    force_all = args.all
    
    print(f"📚 Found {len(all_resources)} resources")
    print(f"🔄 Mode: {'Re-enrich all files' if force_all else 'Enrich only new/changed files'}")
    print("─" * 60 + "\n")
    
    # Run enrichment
    enrichment_engine.enrich_resources(all_resources, commit_hashes, force_all=force_all)
    
    print("\n✅ Enrichment complete!")


if __name__ == "__main__":
    main()
