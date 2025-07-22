import esprima
import json
import os
import sys
import hashlib
import requests
import jsbeautifier
import difflib
import re
from datetime import datetime
from difflib import SequenceMatcher
from src.database import db
from src.models.monitor import MonitoredUrl, DiffFile
from src.services.content_storage import content_storage
from src.services.deobfuscator import deobfuscator
from src.services.notification_service import notification_service
from src.services.logger_service import logger_service
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

monitor_logger = logger_service.get_logger("monitor")

# Add the parent directory to the path to import the original monitor script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

def normalize_javascript_content(js_content):
    """Less aggressive normalization that preserves more meaningful differences."""
    print(f"DEBUG: Normalizing JavaScript content...")
    
    normalized = js_content
    
    # Only remove clearly dynamic content, preserve most changes
    dynamic_patterns = [
        (r'\b\d{13}\b', 'TIMESTAMP_MS'),  # Unix timestamp (milliseconds)
        (r'\b\d{10}\b', 'TIMESTAMP_S'),   # Unix timestamp (seconds)  
        (r'Date\.now\(\)', 'DATE_NOW()'),  # Date.now() calls
        (r'new Date\(\)\.getTime\(\)', 'NEW_DATE_GETTIME()'),  # getTime() calls
        # Remove cache-busting but preserve version changes
        (r'[\?&]_=[\w\d]+', ''),  # ?_=cachebuster only
        (r'[\?&]bust=[\w\d]+', ''),  # ?bust=value only
    ]
    
    for pattern, replacement in dynamic_patterns:
        normalized = re.sub(pattern, replacement, normalized)
    
    # DON'T normalize whitespace aggressively - preserve formatting changes
    # Only remove excessive blank lines
    normalized = re.sub(r'\n\s*\n\s*\n+', '\n\n', normalized)
    
    print(f"DEBUG: Normalization complete. Original: {len(js_content)} chars, Normalized: {len(normalized)} chars")
    return normalized.strip()


def compare_chunk_hashes(old_hash_info, new_hash_info):
    """Compare chunked hashes to detect which parts of the file changed - IMPROVED for small changes."""
    if old_hash_info.get('method') != 'position_aware_chunked' or new_hash_info.get('method') != 'position_aware_chunked':
        return None
    
    old_chunks = old_hash_info.get('chunk_details', [])
    new_chunks = new_hash_info.get('chunk_details', [])
    
    changed_chunks = []
    
    # Compare chunks by position
    max_chunks = max(len(old_chunks), len(new_chunks))
    
    for i in range(max_chunks):
        old_chunk = old_chunks[i] if i < len(old_chunks) else None
        new_chunk = new_chunks[i] if i < len(new_chunks) else None
        
        if not old_chunk or not new_chunk:
            # Chunk added or removed
            changed_chunks.append({
                'chunk_index': i,
                'change_type': 'added' if new_chunk else 'removed',
                'weight': (new_chunk or old_chunk).get('weight', 1.0)
            })
        elif old_chunk['hash'] != new_chunk['hash']:
            # Chunk content changed
            changed_chunks.append({
                'chunk_index': i,
                'change_type': 'modified', 
                'weight': new_chunk.get('weight', 1.0),
                'start': new_chunk.get('start', 0),
                'end': new_chunk.get('end', 0)
            })
    
    if not changed_chunks:
        return {'changed': False, 'confidence': 0.98}
    
    # NEW: Calculate confidence with emphasis on early/important chunks
    total_weight = sum(chunk.get('weight', 1.0) for chunk in old_chunks + new_chunks)
    changed_weight = sum(chunk['weight'] for chunk in changed_chunks)
    change_ratio = changed_weight / total_weight if total_weight > 0 else 1.0
    
    # NEW: Boost confidence if important chunks (early ones) changed
    has_important_change = any(
        chunk['chunk_index'] <= 1 and chunk['weight'] >= 2.0 
        for chunk in changed_chunks
    )
    
    # NEW: Any hash change = high confidence (because MD5 is very sensitive)
    base_confidence = 0.85  # Start higher
    
    if has_important_change:
        # Changes in first 2 chunks get extra confidence boost
        confidence = min(0.98, base_confidence + 0.10)
        print(f"DEBUG: Important chunk changed - boosted confidence to {confidence}")
    else:
        # Regular chunks still get good confidence
        confidence = min(0.95, base_confidence + (change_ratio * 0.10))
    
    print(f"DEBUG: Chunk analysis - {len(changed_chunks)} chunks changed, change ratio: {change_ratio:.3f}, confidence: {confidence:.3f}")
    
    # If ANY chunk hash changed, we should trust it (MD5 is very reliable)
    return {
        'changed': True,
        'confidence': confidence,
        'changed_chunks': changed_chunks,
        'change_ratio': change_ratio,
        'has_important_change': has_important_change
    }



def clean_ast_for_hashing(ast_node, max_depth=10, current_depth=0):
    """Clean AST node of position-dependent and irrelevant data with depth limit."""
    if current_depth > max_depth:
        return "MAX_DEPTH_REACHED"
    
    if isinstance(ast_node, dict):
        cleaned = {}
        for key, value in ast_node.items():
            # Skip position and location data
            if key in ['range', 'loc', 'start', 'end', 'line', 'column', 'index']:
                continue
            # Skip circular references and complex objects
            if key in ['parent', 'raw', 'regex']:
                continue
            cleaned[key] = clean_ast_for_hashing(value, max_depth, current_depth + 1)
        return cleaned
    elif isinstance(ast_node, list):
        return [clean_ast_for_hashing(item, max_depth, current_depth + 1) for item in ast_node]
    elif hasattr(ast_node, '__dict__'):
        # Handle esprima objects by converting to simple dict
        return clean_ast_for_hashing(ast_node.__dict__, max_depth, current_depth + 1)
    else:
        # Handle primitive types and unknown objects
        if isinstance(ast_node, (str, int, float, bool, type(None))):
            return ast_node
        else:
            return str(type(ast_node).__name__)  # Convert complex objects to type name




# Update the confidence threshold check in monitor_single_url
def should_do_additional_verification(change_result):
    """Determine if we need additional verification based on confidence."""
    # Only verify very low confidence changes
    threshold = 0.75  # Reduced from 0.80
    
    # NEW: Skip verification for chunk-based changes with important chunks
    if change_result.get('has_important_change', False):
        threshold = 0.70  # Even lower for important chunks
    
    needs_verification = change_result['confidence'] < threshold
    print(f"DEBUG: Verification check - confidence: {change_result['confidence']:.3f}, threshold: {threshold}, needs_verification: {needs_verification}")
    
    return needs_verification

def clean_problematic_js_patterns(js_content):
    """Remove JavaScript patterns that commonly cause parsing issues."""
    cleaned = js_content
    
    # Remove template literals that might have embedded HTML/CSS
    cleaned = re.sub(r'`[^`]*`', '`TEMPLATE_PLACEHOLDER`', cleaned)
    
    # Remove complex regex patterns
    cleaned = re.sub(r'/[^/\n]+/[gimsuvy]*', '/REGEX_PLACEHOLDER/g', cleaned)
    
    # Remove potential eval/Function constructor calls
    cleaned = re.sub(r'eval\s*\([^)]+\)', 'eval("EVAL_PLACEHOLDER")', cleaned)
    cleaned = re.sub(r'Function\s*\([^)]+\)', 'Function("FUNCTION_PLACEHOLDER")', cleaned)
    
    return cleaned

def generate_semantic_content_hash(js_content):
    """Generate hash based on semantic content rather than exact text."""
    # Remove all comments and strings, focus on structure
    semantic_content = js_content
    
    # Remove string literals
    semantic_content = re.sub(r'"[^"]*"', '"STRING"', semantic_content)
    semantic_content = re.sub(r"'[^']*'", "'STRING'", semantic_content)
    
    # Remove numeric literals (but keep structure)
    semantic_content = re.sub(r'\b\d+(\.\d+)?\b', 'NUMBER', semantic_content)
    
    # Remove comments
    semantic_content = re.sub(r'//.*$', '', semantic_content, flags=re.MULTILINE)
    semantic_content = re.sub(r'/\*.*?\*/', '', semantic_content, flags=re.DOTALL)
    
    # Normalize whitespace completely
    semantic_content = re.sub(r'\s+', ' ', semantic_content).strip()
    
    return hashlib.md5(semantic_content.encode()).hexdigest()

def generate_position_aware_hash(js_content, chunk_size=1500):  # Reduced from 2000
    """Generate hash that's more sensitive to small changes."""
    print(f"DEBUG: generate_position_aware_hash called with content length: {len(js_content)}")
    
    if len(js_content) <= chunk_size:
        # Small file - use simple hash
        content_hash = hashlib.md5(js_content.encode()).hexdigest()
        return {
            'hash': content_hash,
            'method': 'simple_content',
            'confidence': 0.9,
            'chunks': 1
        }
    
    # Large file - split into smaller, more overlapping chunks
    chunks = []
    chunk_hashes = []
    
    # More overlap for better change detection
    overlap = chunk_size // 3  # 33% overlap instead of 50%
    
    for i in range(0, len(js_content), chunk_size - overlap):
        chunk = js_content[i:i + chunk_size]
        if len(chunk) < 100:  # Skip tiny chunks at the end
            continue
            
        # Less aggressive normalization for small change sensitivity
        normalized_chunk = chunk.strip()  # Just strip whitespace
        chunk_hash = hashlib.md5(normalized_chunk.encode()).hexdigest()
        
        # Weight chunks differently - beginning of file is more important
        chunk_number = len(chunk_hashes)
        if chunk_number == 0:
            weight = 4.0  # First chunk gets 4x weight (increased from 3x)
        elif chunk_number == 1:
            weight = 3.0  # Second chunk gets 3x weight (increased from 2x)
        elif chunk_number == 2:
            weight = 2.0  # Third chunk gets 2x weight (new)
        else:
            weight = 1.0  # Other chunks get normal weight
            
        chunk_hashes.append((chunk_hash, weight))
        chunks.append({
            'start': i,
            'end': i + len(chunk),
            'hash': chunk_hash,
            'weight': weight
        })
    
    # Create weighted combined hash
    weighted_hash_parts = []
    for chunk_hash, weight in chunk_hashes:
        # Repeat hash based on weight
        for _ in range(int(weight)):
            weighted_hash_parts.append(chunk_hash)
    
    combined_hash = hashlib.md5(''.join(weighted_hash_parts).encode()).hexdigest()
    
    print(f"DEBUG: Created {len(chunks)} chunks (size: {chunk_size}, overlap: {overlap}) with weighted hash: {combined_hash}")
    
    return {
        'hash': combined_hash,
        'method': 'position_aware_chunked',
        'confidence': 0.92,
        'chunks': len(chunks),
        'chunk_details': chunks
    }

def generate_position_aware_hash(js_content, chunk_size=2000):
    """Generate hash that's sensitive to changes in different parts of the file."""
    print(f"DEBUG: generate_position_aware_hash called with content length: {len(js_content)}")
    
    if len(js_content) <= chunk_size:
        # Small file - use simple hash
        content_hash = hashlib.md5(js_content.encode()).hexdigest()
        return {
            'hash': content_hash,
            'method': 'simple_content',
            'confidence': 0.9,
            'chunks': 1
        }
    
    # Large file - split into weighted chunks
    chunks = []
    chunk_hashes = []
    
    # Split into overlapping chunks for better change detection
    for i in range(0, len(js_content), chunk_size // 2):  # 50% overlap
        chunk = js_content[i:i + chunk_size]
        if len(chunk) < 100:  # Skip tiny chunks at the end
            continue
            
        # Normalize chunk
        normalized_chunk = normalize_javascript_content(chunk)
        chunk_hash = hashlib.md5(normalized_chunk.encode()).hexdigest()
        
        # Weight chunks differently - beginning of file is more important
        chunk_number = len(chunk_hashes)
        if chunk_number == 0:
            weight = 3.0  # First chunk gets 3x weight
        elif chunk_number == 1:
            weight = 2.0  # Second chunk gets 2x weight
        else:
            weight = 1.0  # Other chunks get normal weight
            
        chunk_hashes.append((chunk_hash, weight))
        chunks.append({
            'start': i,
            'end': i + len(chunk),
            'hash': chunk_hash,
            'weight': weight
        })
    
    # Create weighted combined hash
    weighted_hash_parts = []
    for chunk_hash, weight in chunk_hashes:
        # Repeat hash based on weight
        for _ in range(int(weight)):
            weighted_hash_parts.append(chunk_hash)
    
    combined_hash = hashlib.md5(''.join(weighted_hash_parts).encode()).hexdigest()
    
    print(f"DEBUG: Created {len(chunks)} chunks with weighted hash: {combined_hash}")
    
    return {
        'hash': combined_hash,
        'method': 'position_aware_chunked',
        'confidence': 0.92,
        'chunks': len(chunks),
        'chunk_details': chunks
    }

def generate_enhanced_ast_hash(js_content):
    """Generate AST hash with improved error handling and large file support."""
    print(f"DEBUG: generate_enhanced_ast_hash called with content length: {len(js_content)}")
    
    # For very large files, use position-aware chunking instead of AST
    if len(js_content) > 10000:  # 10KB+ files
        print(f"DEBUG: Large file detected, using position-aware chunking")
        return generate_position_aware_hash(js_content)
    
    # First, try to normalize the content
    try:
        normalized_content = normalize_javascript_content(js_content)
    except Exception as e:
        print(f"DEBUG: Normalization failed: {e}")
        normalized_content = js_content
    
    # Primary method: AST hashing (for smaller files)
    try:
        ast = esprima.parseScript(normalized_content, options={
            'tolerant': True,
            'range': False,
            'loc': False,
            'attachComments': False
        })
        
        print(f"DEBUG: AST parsed successfully, type: {type(ast)}")
        
        # Remove position-dependent data from AST
        ast_cleaned = clean_ast_for_hashing(ast)
        print(f"DEBUG: AST cleaned successfully")
        
        # Convert to JSON string for hashing
        try:
            ast_json = json.dumps(ast_cleaned, sort_keys=True, default=str)
            ast_hash = hashlib.md5(ast_json.encode()).hexdigest()
            
            print(f"DEBUG: AST hash generated successfully: {ast_hash}")
            return {
                'hash': ast_hash,
                'method': 'ast',
                'confidence': 0.95,
                'normalized': True
            }
        except Exception as json_error:
            print(f"DEBUG: JSON serialization failed: {json_error}")
            # Fall through to chunked method
            
    except Exception as ast_error:
        print(f"DEBUG: AST parsing failed: {ast_error}")
    
    # Fallback: Use position-aware chunking for better detection
    print(f"DEBUG: Using position-aware chunking as fallback")
    return generate_position_aware_hash(js_content)


def calculate_change_confidence(old_hash_info, new_hash_info, content_similarity=None):
    """Calculate confidence level for detected changes - IMPROVED for small changes."""
    if old_hash_info['hash'] == new_hash_info['hash']:
        return {'changed': False, 'confidence': 0.99}
    
    # Special handling for chunked hashes
    chunk_result = compare_chunk_hashes(old_hash_info, new_hash_info)
    if chunk_result:
        print(f"DEBUG: Chunk comparison result: {chunk_result}")
        
        # NEW: If chunk hashes differ, trust them more than similarity
        if chunk_result['changed'] and chunk_result['confidence'] >= 0.85:
            print(f"DEBUG: High confidence chunk change - skipping similarity check")
            return chunk_result
        
        # Only do similarity check for lower confidence changes
        if content_similarity is not None:
            similarity = content_similarity['similarity']
            print(f"DEBUG: Doing similarity check for chunk change, similarity: {similarity:.4f}")
            
            # NEW: More lenient similarity thresholds when chunks changed
            if chunk_result.get('has_important_change', False):
                # Important chunks changed - be very permissive with similarity
                if similarity < 0.999:  # Even 99.9% similarity = real change if important chunk changed
                    print(f"DEBUG: Important chunk changed with {similarity:.4f} similarity - confirming change")
                    return {'changed': True, 'confidence': min(chunk_result['confidence'] * 1.05, 0.98)}
            else:
                # Regular chunks - still be more permissive than before
                if similarity < 0.995:  # 99.5% threshold instead of 97%
                    return {'changed': True, 'confidence': chunk_result['confidence']}
            
            # Very high similarity - might be false positive
            print(f"DEBUG: Very high similarity ({similarity:.4f}) - treating as no change")
            return {'changed': False, 'confidence': 0.90}
        
        return chunk_result
    
    # Non-chunked methods - existing logic
    if content_similarity is not None:
        similarity = content_similarity['similarity']
        length_diff = content_similarity['length_diff']
        
        print(f"DEBUG: Similarity analysis - similarity: {similarity:.4f}, length_diff: {length_diff:.4f}")
        
        # For non-chunked, use original thresholds
        if similarity > 0.98 and length_diff < 0.01:
            return {'changed': False, 'confidence': 0.95}
        
        if similarity > 0.95:
            base_confidence = min(old_hash_info['confidence'], new_hash_info['confidence'])
            return {'changed': True, 'confidence': base_confidence * 0.9}
        
        # Lower similarity - definitely changed
        base_confidence = min(old_hash_info['confidence'], new_hash_info['confidence'])
        return {'changed': True, 'confidence': min(base_confidence * 1.1, 0.99)}
    
    # Default case - hashes are different
    base_confidence = min(old_hash_info['confidence'], new_hash_info['confidence'])
    return {'changed': True, 'confidence': base_confidence}


def enhanced_content_comparison(old_content, new_content):
    """Enhanced comparison that considers semantic similarity."""
    # Quick length check
    old_len = len(old_content)
    new_len = len(new_content)
    max_len = max(old_len, new_len)
    
    if max_len == 0:
        return {'similarity': 1.0, 'major_change': False, 'length_diff': 0.0}
    
    length_diff = abs(old_len - new_len) / max_len
    
    print(f"DEBUG: Length comparison - old: {old_len}, new: {new_len}, diff: {length_diff:.4f}")
    
    # Major size difference indicates significant change
    if length_diff > 0.3:  # More than 30% size difference
        return {'similarity': 0.0, 'major_change': True, 'length_diff': length_diff}
    
    # Line-by-line similarity using difflib
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    
    from difflib import SequenceMatcher
    matcher = SequenceMatcher(None, old_lines, new_lines)
    similarity = matcher.ratio()
    
    print(f"DEBUG: Line-by-line similarity: {similarity:.4f}")
    
    # Additional character-level check for small files
    if max_len < 1000:  # Small files - do character-level comparison too
        char_matcher = SequenceMatcher(None, old_content, new_content)
        char_similarity = char_matcher.ratio()
        # Use the higher of the two similarities for small files
        similarity = max(similarity, char_similarity)
        print(f"DEBUG: Character-level similarity: {char_similarity:.4f}, using: {similarity:.4f}")
    
    return {
        'similarity': similarity,
        'major_change': similarity < 0.7 or length_diff > 0.2,
        'length_diff': length_diff
    }

# Legacy function for backward compatibility
def generate_ast_hash(js_content):
    """Legacy AST hash function - now uses enhanced version."""
    result = generate_enhanced_ast_hash(js_content)
    return result['hash']

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.exceptions.RequestException))
def download_javascript(url):
    """Download JavaScript content from a given URL with retries."""
    print(f"DEBUG: download_javascript called with URL: {url}")
    try:
        print(f"DEBUG: Making HTTP request to: {url}")
        response = requests.get(url, timeout=30)
        print(f"DEBUG: Got response status: {response.status_code}")
        response.raise_for_status()
        print(f"DEBUG: Response content length: {len(response.text)}")
        return response.text
    except requests.RequestException as e:
        print(f"DEBUG: Request exception: {type(e).__name__}: {e}")
        monitor_logger.error(f'Error downloading {url}: {e}')
        raise  # Re-raise the exception to trigger retry

def beautify_javascript(js_content):
    """Beautify JavaScript content using jsbeautifier."""
    print(f"DEBUG: beautify_javascript called with content length: {len(js_content)}")
    try:
        options = jsbeautifier.default_options()
        options.indent_size = 2
        options.max_preserve_newlines = 2
        options.wrap_line_length = 120
        result = jsbeautifier.beautify(js_content, options)
        print(f"DEBUG: JavaScript beautified successfully, result length: {len(result)}")
        return result
    except Exception as e:
        print(f"DEBUG: Error beautifying JavaScript: {e}")
        return js_content  # Return original if beautification fails

def sanitize_url_to_filename(url):
    """Sanitize a URL to create a safe filename."""
    return ''.join([c if c.isalnum() else '_' for c in url])

def chunk_large_content(content, max_chunk_size=50000):
    """Split large content into manageable chunks for processing."""
    if len(content) <= max_chunk_size:
        return [content]
    
    lines = content.split('\n')
    chunks = []
    current_chunk = []
    current_size = 0
    
    for line in lines:
        line_size = len(line) + 1  # +1 for newline
        if current_size + line_size > max_chunk_size and current_chunk:
            chunks.append('\n'.join(current_chunk))
            current_chunk = [line]
            current_size = line_size
        else:
            current_chunk.append(line)
            current_size += line_size
    
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks

def generate_chunk_diff(old_chunk, new_chunk, chunk_number):
    """Generate diff for a single chunk with improved line matching."""
    # Normalize line endings consistently
    old_lines = [line.rstrip('\r\n') for line in old_chunk.splitlines()]
    new_lines = [line.rstrip('\r\n') for line in new_chunk.splitlines()]
    
    # Use SequenceMatcher instead of Differ for better line matching
    from difflib import SequenceMatcher
    matcher = SequenceMatcher(None, old_lines, new_lines)
    
    # Build diff from opcodes
    chunk_html = []
    significant_changes = False
    change_id_base = (chunk_number - 1) * 1000
    change_id = change_id_base + 1
    line_number = 1
    
    if chunk_number > 1:
        chunk_html.append(f'<div class="chunk-header">📦 Chunk {chunk_number}</div>')
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            # Lines are the same - show as context
            for i in range(i1, i2):
                line_content = old_lines[i]
                if line_content.strip() and not line_content.strip().startswith('//'):
                    chunk_html.append(f'<span class="line-number">{line_number:4d}</span>{line_content}<br>')
                line_number += 1
        elif tag == 'delete':
            # Lines removed from old
            for i in range(i1, i2):
                line_content = old_lines[i]
                if line_content.strip() and not line_content.strip().startswith('//'):
                    chunk_html.append(f'<span id="change{change_id}" class="removed"><span class="line-number">{line_number:4d}</span>{line_content}<span class="change-indicator">−</span></span><br>')
                    significant_changes = True
                    change_id += 1
                line_number += 1
        elif tag == 'insert':
            # Lines added to new
            for j in range(j1, j2):
                line_content = new_lines[j]
                if line_content.strip() and not line_content.strip().startswith('//'):
                    chunk_html.append(f'<span id="change{change_id}" class="added"><span class="line-number">{line_number:4d}</span>{line_content}<span class="change-indicator">+</span></span><br>')
                    significant_changes = True
                    change_id += 1
                line_number += 1
        elif tag == 'replace':
            # Lines changed - show both old and new
            # First show deleted lines
            for i in range(i1, i2):
                line_content = old_lines[i]
                if line_content.strip() and not line_content.strip().startswith('//'):
                    chunk_html.append(f'<span id="change{change_id}" class="removed"><span class="line-number">{line_number:4d}</span>{line_content}<span class="change-indicator">−</span></span><br>')
                    significant_changes = True
                    change_id += 1
                line_number += 1
            # Then show added lines  
            for j in range(j1, j2):
                line_content = new_lines[j]
                if line_content.strip() and not line_content.strip().startswith('//'):
                    chunk_html.append(f'<span id="change{change_id}" class="added"><span class="line-number">{line_number:4d}</span>{line_content}<span class="change-indicator">+</span></span><br>')
                    significant_changes = True
                    change_id += 1
                line_number += 1
    
    return ''.join(chunk_html) if significant_changes else None, significant_changes

def generate_enhanced_html_diff(old_content, new_content, url, obfuscation_info=None):
    """Generate an enhanced HTML diff with better highlighting and large file support."""
    print(f"DEBUG: generate_enhanced_html_diff called")
    
    # Handle large files by chunking
    old_chunks = chunk_large_content(old_content)
    new_chunks = chunk_large_content(new_content)
    
    all_diffs = []
    significant_changes = False
    
    # Process each chunk pair
    max_chunks = max(len(old_chunks), len(new_chunks))
    
    for i in range(max_chunks):
        old_chunk = old_chunks[i] if i < len(old_chunks) else ""
        new_chunk = new_chunks[i] if i < len(new_chunks) else ""
        
        chunk_diff, chunk_significant = generate_chunk_diff(old_chunk, new_chunk, i + 1)
        if chunk_diff:
            all_diffs.append(chunk_diff)
            if chunk_significant:
                significant_changes = True
    
    if not significant_changes:
        print(f"DEBUG: No significant changes found in diff")
        return None
    
    # Generate the complete HTML
    style = """
    <style>
        body { 
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace; 
            margin: 0; 
            padding: 10px; 
            background-color: #f8f9fa;
            font-size: 13px;
            line-height: 1.4;
        }
        .container { 
            display: flex; 
            flex-wrap: wrap; 
            gap: 20px; 
            max-width: 100%;
        }
        .column { 
            flex: 1; 
            min-width: 45%;
            padding: 15px; 
            box-sizing: border-box; 
            overflow-x: auto; 
            max-height: 80vh; 
            border: 1px solid #dee2e6; 
            border-radius: 8px; 
            background-color: #ffffff;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .column pre { 
            margin: 0; 
            white-space: pre-wrap; 
            word-wrap: break-word; 
            font-family: inherit;
        }
        .navigation-bar { 
            margin-bottom: 20px; 
            text-align: center; 
            background-color: #e9ecef; 
            padding: 15px; 
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .navigation-bar a { 
            margin: 0 8px; 
            text-decoration: none; 
            color: #007bff; 
            padding: 5px 10px;
            border-radius: 4px;
            background-color: #ffffff;
            border: 1px solid #007bff;
            transition: all 0.2s;
        }
        .navigation-bar a:hover { 
            background-color: #007bff;
            color: #ffffff;
        }
        .removed { 
            background-color: #ffeaea; 
            border-left: 4px solid #dc3545;
            display: block; 
            padding: 4px 8px; 
            margin: 2px 0; 
            border-radius: 4px;
            position: relative;
        }
        .added { 
            background-color: #eafaf1; 
            border-left: 4px solid #28a745;
            display: block; 
            padding: 4px 8px; 
            margin: 2px 0; 
            border-radius: 4px;
            position: relative;
        }
        .modified {
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            display: block;
            padding: 4px 8px;
            margin: 2px 0;
            border-radius: 4px;
            position: relative;
        }
        .line-number {
            color: #6c757d;
            font-size: 11px;
            margin-right: 10px;
            user-select: none;
        }
        .change-indicator {
            position: absolute;
            right: 5px;
            top: 2px;
            font-size: 10px;
            font-weight: bold;
        }
        .removed .change-indicator { color: #dc3545; }
        .added .change-indicator { color: #28a745; }
        .modified .change-indicator { color: #ffc107; }
        .header { 
            text-align: center; 
            margin-bottom: 20px; 
            background-color: #ffffff;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .url-info { 
            background-color: #f8f9fa; 
            padding: 15px; 
            border-radius: 8px; 
            margin-bottom: 20px;
            border: 1px solid #dee2e6;
        }
        .stats {
            display: flex;
            justify-content: space-around;
            margin: 15px 0;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 6px;
        }
        .stat-item {
            text-align: center;
        }
        .stat-number {
            font-size: 18px;
            font-weight: bold;
            color: #495057;
        }
        .stat-label {
            font-size: 12px;
            color: #6c757d;
        }
        .chunk-header {
            background-color: #6c757d;
            color: white;
            padding: 8px 15px;
            margin: 20px 0 10px 0;
            border-radius: 4px;
            font-weight: bold;
        }
        @media (max-width: 768px) {
            .container { flex-direction: column; }
            .column { min-width: 100%; }
        }
    </style>
    """
    
    # Count statistics
    total_additions = sum(chunk.count('class="added"') for chunk in all_diffs)
    total_deletions = sum(chunk.count('class="removed"') for chunk in all_diffs)
    total_modifications = sum(chunk.count('class="modified"') for chunk in all_diffs)
    
    # Generate navigation links
    change_links = []
    change_id = 1
    for chunk in all_diffs:
        chunk_changes = chunk.count('id="change')
        for _ in range(chunk_changes):
            change_links.append(f'<a href="#change{change_id}">Change {change_id}</a>')
            change_id += 1
    
    navigation_bar = '<div class="navigation-bar">' + ' | '.join(change_links) + '</div>' if change_links else ''
    
    # Obfuscation information section
    obfuscation_section = ""
    if obfuscation_info:
        obfuscation_section = f'''
        <div class="obfuscation-info" style="background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
            <h4>🔒 Obfuscation Analysis</h4>
            <div style="font-weight: bold; color: #856404;">Obfuscation Score: {obfuscation_info.get('score', 0):.2f}/1.00</div>
            <div>Detected Techniques: {', '.join([k.replace('_', ' ').title() for k, v in obfuscation_info.get('detection', {}).items() if v])}</div>
        </div>
        '''
    
    header = f'''
    <div class="header">
        <h1>JavaScript Change Detection Report</h1>
        <div class="url-info">
            <strong>URL:</strong> {url}<br>
            <strong>Generated:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}<br>
            <strong>File Size:</strong> Old: {len(old_content):,} chars, New: {len(new_content):,} chars
        </div>
        {obfuscation_section}
        <div class="stats">
            <div class="stat-item">
                <div class="stat-number" style="color: #28a745;">{total_additions}</div>
                <div class="stat-label">Additions</div>
            </div>
            <div class="stat-item">
                <div class="stat-number" style="color: #dc3545;">{total_deletions}</div>
                <div class="stat-label">Deletions</div>
            </div>
            <div class="stat-item">
                <div class="stat-number" style="color: #ffc107;">{total_modifications}</div>
                <div class="stat-label">Modifications</div>
            </div>
        </div>
    </div>
    '''
    
    # Combine all content
    diff_content = '<div style="font-family: monospace; white-space: pre-wrap;">' + ''.join(all_diffs) + '</div>'
    
    combined_html = style + header + navigation_bar + diff_content + navigation_bar
    
    print(f"DEBUG: Generated HTML diff successfully with {len(combined_html)} characters")
    return combined_html

def save_diff_file(html_content, url, url_id):
    """Save diff HTML content to file and database."""
    print(f"DEBUG: save_diff_file called for URL ID: {url_id}")
    try:
        # Create diffs directory if it doesn't exist
        diffs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'diffs')
        os.makedirs(diffs_dir, exist_ok=True)
        
        # Generate filename
        sanitized_url = sanitize_url_to_filename(url)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"diff_{sanitized_url}_{timestamp}.html"
        file_path = os.path.join(diffs_dir, filename)
        
        # Save HTML content to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Generate preview (extract key statistics)
        additions = html_content.count('class="added"')
        deletions = html_content.count('class="removed"')
        modifications = html_content.count('class="modified"')
        
        preview = f"📊 Changes: +{additions} additions, -{deletions} deletions, ~{modifications} modifications"
        
        # Save to database
        diff_file = DiffFile(
            filename=filename,
            file_path=file_path,
            url_id=url_id,
            file_size=len(html_content.encode('utf-8')),
            preview=preview
        )
        db.session.add(diff_file)
        db.session.commit()
        
        print(f"DEBUG: Diff file saved successfully: {filename}")
        return diff_file
    except Exception as e:
        print(f"DEBUG: Error saving diff file: {e}")
        raise

def monitor_single_url(monitored_url):
    """Enhanced monitoring with better change detection."""
    print(f"DEBUG: Starting enhanced monitoring for URL: {monitored_url.url}")
    try:
        # Download current content
        print(f"DEBUG: Attempting to download: {monitored_url.url}")
        content = download_javascript(monitored_url.url)
        if content is None:
            print(f"DEBUG: download_javascript returned None for {monitored_url.url}")
            monitor_logger.error(f"Failed to download {monitored_url.url}", extra={
                "url": monitored_url.url,
                "event_type": "download_failed"
            })
            return {"success": False, "message": f"Failed to download {monitored_url.url}"}
        
        print(f"DEBUG: Successfully downloaded {len(content)} characters from {monitored_url.url}")
        
        # Analyze obfuscation
        print(f"DEBUG: Starting obfuscation analysis...")
        obfuscation_score = deobfuscator.get_obfuscation_score(content)
        obfuscation_detection = deobfuscator.detect_obfuscation_type(content)
        print(f"DEBUG: Obfuscation analysis complete. Score: {obfuscation_score}")
        
        # Deobfuscate if needed (score > 0.3 indicates likely obfuscation)
        deobfuscation_stats = {}
        if obfuscation_score > 0.3:
            print(f"DEBUG: Deobfuscating content...")
            content, deobfuscation_stats = deobfuscator.deobfuscate(content)
            print(f"DEBUG: Deobfuscation complete")
        
        # Beautify content
        print(f"DEBUG: Beautifying content...")
        content = beautify_javascript(content)
        print(f"DEBUG: Content beautified")
        
        # Enhanced hash generation
        print(f"DEBUG: Generating enhanced AST hash...")
        current_hash_info = generate_enhanced_ast_hash(content)
        print(f"DEBUG: Generated enhanced hash: {current_hash_info}")
        
        # Get previous hash info (enhanced detection)
        if hasattr(monitored_url, 'last_hash_info') and monitored_url.last_hash_info:
            try:
                old_hash_info = json.loads(monitored_url.last_hash_info)
            except:
                old_hash_info = {
                    'hash': monitored_url.last_hash,
                    'method': 'legacy',
                    'confidence': 0.5,
                    'normalized': False
                }
        else:
            # First run or legacy data
            old_hash_info = {
                'hash': monitored_url.last_hash,
                'method': 'legacy',
                'confidence': 0.5,
                'normalized': False
            }
        
        # Enhanced change detection
        if old_hash_info['hash']:
            change_result = calculate_change_confidence(old_hash_info, current_hash_info)
            print(f"DEBUG: Change detection result: {change_result}")
            
            # UPDATED: Use better threshold for additional verification
            if change_result['confidence'] < 0.80:  # Changed from 0.7 to 0.85
                # Low confidence, do additional checks
                print(f"DEBUG: Low confidence change, doing additional verification...")
                previous_content = content_storage.get_previous_content(monitored_url.id)
                if previous_content:
                    comparison = enhanced_content_comparison(previous_content, content)
                    print(f"DEBUG: Content comparison: {comparison}")
                    change_result = calculate_change_confidence(
                        old_hash_info, 
                        current_hash_info, 
                        comparison
                    )
                    print(f"DEBUG: Revised change detection result: {change_result}")
            
            if not change_result['changed']:
                print(f"DEBUG: No significant changes detected (confidence: {change_result['confidence']})")
                monitored_url.last_checked = datetime.utcnow()
                db.session.commit()
                return {
                    "success": True, 
                    "message": f"No changes detected for {monitored_url.url} (confidence: {change_result['confidence']:.2f})", 
                    "changed": False,
                    "confidence": change_result['confidence'],
                    "method": current_hash_info['method']
                }
        
        print(f"DEBUG: Content has changed or this is first check")
        
        # Store current content
        print(f"DEBUG: Storing content...")
        content_storage.store_content(monitored_url.id, content, current_hash_info['hash'])
        print(f"DEBUG: Content stored successfully")
        
        # Content has changed or this is the first check
        if old_hash_info['hash']:
            print(f"DEBUG: This is a change (not first check)")
            # Get previous content for comparison
            previous_content = content_storage.get_previous_content(monitored_url.id)
            
            if previous_content:
                print(f"DEBUG: Got previous content, generating diff...")
                # Prepare obfuscation info for diff
                obfuscation_info = {
                    'score': obfuscation_score,
                    'detection': obfuscation_detection,
                    'deobfuscation_stats': deobfuscation_stats
                }
                
                # Generate enhanced HTML diff
                html_diff = generate_enhanced_html_diff(
                    previous_content, 
                    content, 
                    monitored_url.url,
                    obfuscation_info
                )
                
                if html_diff:
                    print(f"DEBUG: HTML diff generated, saving diff file...")
                    # Save diff file
                    diff_file = save_diff_file(html_diff, monitored_url.url, monitored_url.id)
                    message = f'Changes detected for {monitored_url.url}. Enhanced diff saved as {diff_file.filename}'
                    changed = True
                    print(f"DEBUG: Diff file saved, sending notification...")
                    # Send Discord notification
                    notification_service.send_discord_notification(f'Changes detected for {monitored_url.url}! Check diff: {diff_file.filename}')
                    print(f"DEBUG: Notification sent")
                else:
                    message = f'No significant changes detected for {monitored_url.url}'
                    changed = False
                    print(f"DEBUG: No significant changes")
            else:
                message = f'Changes detected for {monitored_url.url}, but no previous content available for comparison'
                changed = True
                print(f"DEBUG: No previous content available")
        else:
            message = f'First check completed for {monitored_url.url}'
            if obfuscation_score > 0.3:
                message += f' (Obfuscation detected: {obfuscation_score:.2f})'
            changed = False
            print(f"DEBUG: First check completed")
        
        # Update URL record with enhanced hash info
        print(f"DEBUG: Updating URL record in database...")
        monitored_url.last_hash = current_hash_info['hash']
        if hasattr(monitored_url, 'last_hash_info'):
            monitored_url.last_hash_info = json.dumps(current_hash_info)
        monitored_url.last_checked = datetime.utcnow()
        db.session.commit()
        print(f"DEBUG: URL record updated successfully")
        
        change_confidence = change_result['confidence'] if 'change_result' in locals() else current_hash_info['confidence']
        
        print(f"DEBUG: Monitoring completed successfully")
        return {
            'success': True, 
            'message': message, 
            'changed': changed,
            'confidence': change_confidence,
            'method': current_hash_info['method']
        }
        
    except Exception as e:
        print(f"DEBUG: Exception in monitor_single_url: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        logger_service.log_error(e, context={
            "url": monitored_url.url,
            "function": "monitor_single_url"
        })
        return {"success": False, "message": f"Error monitoring {monitored_url.url}: {str(e)}"}

def run_monitoring_check():
    """Run monitoring check for all active URLs."""
    print(f"DEBUG: run_monitoring_check started")
    monitor_logger.info("Starting scheduled monitoring check.")
    active_urls = MonitoredUrl.query.filter_by(active=True).all()
    
    if not active_urls:
        print(f"DEBUG: No active URLs found")
        monitor_logger.info("No active URLs to monitor.")
        return {
            "message": "No active URLs to monitor",
            "changes_detected": False,
            "urls_checked": 0
        }
    
    print(f"DEBUG: Found {len(active_urls)} active URLs")
    results = []
    changes_detected = False
    
    for url in active_urls:
        print(f"DEBUG: Processing URL: {url.url}")
        result = monitor_single_url(url)
        print(f"DEBUG: Result for {url.url}: {result}")
        results.append(result)
        
        if result.get("changed", False):
            changes_detected = True
    
    successful_checks = sum(1 for r in results if r["success"])
    failed_checks = len(results) - successful_checks
    
    print(f"DEBUG: Monitoring summary - Total: {len(active_urls)}, Successful: {successful_checks}, Failed: {failed_checks}")
    
    if failed_checks > 0:
        message = f"Checked {len(active_urls)} URLs. {successful_checks} successful, {failed_checks} failed."
        monitor_logger.warning(message, extra={
            "event_type": "monitoring_summary",
            "total_urls": len(active_urls),
            "successful": successful_checks,
            "failed": failed_checks
        })
    else:
        message = f"Successfully checked {len(active_urls)} URLs."
        monitor_logger.info(message, extra={
            "event_type": "monitoring_summary",
            "total_urls": len(active_urls),
            "successful": successful_checks,
            "failed": failed_checks
        })
    
    if changes_detected:
        message += " 🎉 Changes detected!"
        monitor_logger.info("Changes detected during this monitoring run.", extra={
            "event_type": "overall_changes_detected"
        })
    
    print(f"DEBUG: run_monitoring_check completed")
    return {
        "message": message,
        "changes_detected": changes_detected,
        "urls_checked": len(active_urls),
        "results": results
    }