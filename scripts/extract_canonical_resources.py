#!/usr/bin/env python3
"""
Canonical Resource Extractor CLI

Extracts canonical resources from Git-verified documentation repositories
and creates YAML resources with integrity verification.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from canton_mcp_server.core.resource_extractor import GitVerifiedResourceExtractor, ResourceExtractionError

def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract canonical resources from Git-verified documentation"
    )
    
    parser.add_argument(
        "--canonical-docs",
        type=Path,
        default=Path("../canonical-daml-docs"),
        help="Path to canonical documentation repositories"
    )
    
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("resources"),
        help="Output directory for extracted resources"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="Only sync repositories, don't extract resources"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize extractor
        extractor = GitVerifiedResourceExtractor(args.canonical_docs)
        
        if args.sync_only:
            # Just sync repositories
            logger.info("Syncing canonical repositories...")
            commit_hashes = extractor.sync_repositories()
            logger.info(f"Sync complete. Latest commits: {commit_hashes}")
            return
        
        # Extract all resources
        logger.info("Starting canonical resource extraction...")
        resources = extractor.extract_all_resources(args.output)
        
        # Print summary
        total_resources = sum(len(resource_list) for resource_list in resources.values())
        logger.info("Extraction complete!")
        logger.info(f"Total resources extracted: {total_resources}")
        
        for resource_type, resource_list in resources.items():
            if resource_list:
                logger.info(f"  {resource_type}: {len(resource_list)} resources")
        
        logger.info(f"Resources saved to: {args.output}")
        
    except ResourceExtractionError as e:
        logger.error(f"Resource extraction failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
