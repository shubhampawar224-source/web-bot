#!/usr/bin/env python3
"""
Simple script to compact the FAISS metadata file by removing indentation
"""

import json
import os

def compact_metadata():
    """Remove indentation from metadata.json to reduce file size"""
    metadata_file = "rag_db_faiss/metadata.json"
    
    if os.path.exists(metadata_file):
        print(f"📊 Original file size: {os.path.getsize(metadata_file):,} bytes")
        
        # Load the data
        with open(metadata_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Save without indentation
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        
        print(f"📊 Compacted file size: {os.path.getsize(metadata_file):,} bytes")
        print("✅ Metadata file compacted successfully!")
    else:
        print("❌ Metadata file not found")

if __name__ == "__main__":
    compact_metadata()